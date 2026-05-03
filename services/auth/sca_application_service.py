"""
services/auth/sca_application_service.py — Application boundary for PSD2 SCA orchestration
S15-01 / Sprint 4 Track A | banxe-emi-stack

Mirrors the AuthApplicationService pattern: thin orchestration layer between
the HTTP router (api/routers/auth.py SCA endpoints) and the SCA domain
service (services/auth/sca_service.py).

Responsibilities:
    - Coordinate challenge lifecycle (initiate, verify, resend, list methods)
    - Translate domain exceptions (RuntimeError/KeyError/ValueError) into
      ScaApplicationError with stable error codes
    - Map domain results (SCAChallenge / SCAVerifyResult / SCAMethods) to
      HTTP response models via api/models/sca_adapters.py

Rule: router must not see domain dataclasses; ScaApplicationService is the
seam where domain ↔ transport translation happens.
"""

from __future__ import annotations

import logging
from typing import Any

from api.models.sca import (
    SCAInitiateResponse,
    SCAMethodsResponse,
    SCAResendResponse,
    SCAVerifyResponse,
)
from api.models.sca_adapters import (
    to_sca_initiate_response,
    to_sca_methods_response,
    to_sca_resend_response,
    to_sca_verify_response,
)
from services.auth.sca_service import get_sca_service
from services.auth.sca_service_port import ScaServicePort

logger = logging.getLogger("banxe.auth.sca_app")


class ScaApplicationError(Exception):
    """Translated SCA domain error with stable code for HTTP mapping."""

    def __init__(self, message: str, code: str = "sca_error") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class ScaApplicationService:
    """Application boundary for SCA challenge lifecycle orchestration."""

    def __init__(self, sca_service: ScaServicePort | None = None) -> None:
        self.sca_service: Any = sca_service or get_sca_service()

    def initiate_challenge(
        self,
        *,
        customer_id: str,
        transaction_id: str,
        method: str,
        amount: str | None = None,
        payee: str | None = None,
    ) -> SCAInitiateResponse:
        try:
            challenge = self.sca_service.create_challenge(
                customer_id=customer_id,
                transaction_id=transaction_id,
                method=method,
                amount=amount,
                payee=payee,
            )
        except ValueError as exc:
            raise ScaApplicationError(str(exc), code="invalid_method") from exc
        except RuntimeError as exc:
            raise ScaApplicationError(str(exc), code="too_many_active") from exc
        logger.info(
            "sca_app.challenge_initiated challenge_id=%s customer=%s",
            challenge.challenge_id,
            customer_id,
        )
        return to_sca_initiate_response(challenge)

    def verify_challenge(
        self,
        *,
        challenge_id: str,
        otp_code: str | None = None,
        biometric_proof: str | None = None,
    ) -> SCAVerifyResponse:
        result = self.sca_service.verify(
            challenge_id=challenge_id,
            otp_code=otp_code,
            biometric_proof=biometric_proof,
        )
        if result.error == "Challenge not found":
            raise ScaApplicationError("Challenge not found", code="challenge_not_found")
        if not result.verified and result.attempts_remaining == 0:
            raise ScaApplicationError(
                "Too many failed attempts. Request a new challenge.",
                code="too_many_attempts",
            )
        return to_sca_verify_response(result)

    def resend_challenge(self, *, challenge_id: str) -> SCAResendResponse:
        try:
            challenge = self.sca_service.resend_challenge(challenge_id)
        except KeyError as exc:
            raise ScaApplicationError(str(exc), code="challenge_not_found") from exc
        except ValueError as exc:
            raise ScaApplicationError(str(exc), code="resend_rejected") from exc
        return to_sca_resend_response(challenge)

    def list_methods(self, *, customer_id: str) -> SCAMethodsResponse:
        methods = self.sca_service.get_methods(customer_id)
        return to_sca_methods_response(methods)


_sca_app_service: ScaApplicationService | None = None


def get_sca_application_service() -> ScaApplicationService:
    """Dependency provider for FastAPI SCA application service (singleton)."""
    global _sca_app_service  # noqa: PLW0603
    if _sca_app_service is None:
        _sca_app_service = ScaApplicationService()
    return _sca_app_service
