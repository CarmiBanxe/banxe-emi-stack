"""
api/models/sca_adapters.py — Domain → HTTP response adapters for SCA.

Isolates router from SCA domain types (SCAChallenge, SCAVerifyResult, SCAMethods)
so that domain model changes don't leak into HTTP contract.

Canon: router must not know dataclass internals (ADR-015).
"""

from __future__ import annotations

from api.models.sca import (
    SCAInitiateResponse,
    SCAMethodsResponse,
    SCAResendResponse,
    SCAVerifyResponse,
)
from services.auth.sca_models import SCAChallenge, SCAMethods, SCAVerifyResult


def to_sca_initiate_response(challenge: SCAChallenge) -> SCAInitiateResponse:
    return SCAInitiateResponse(
        challenge_id=challenge.challenge_id,
        transaction_id=challenge.transaction_id,
        method=challenge.method,
        expires_at=challenge.expires_at,
    )


def to_sca_verify_response(result: SCAVerifyResult) -> SCAVerifyResponse:
    return SCAVerifyResponse(
        verified=result.verified,
        transaction_id=result.transaction_id,
        sca_token=result.sca_token,
        error=result.error,
        attempts_remaining=result.attempts_remaining,
    )


def to_sca_resend_response(challenge: SCAChallenge) -> SCAResendResponse:
    return SCAResendResponse(
        challenge_id=challenge.challenge_id,
        method=challenge.method,
        expires_at=challenge.expires_at,
        resend_count=challenge.resend_count,
    )


def to_sca_methods_response(methods: SCAMethods) -> SCAMethodsResponse:
    return SCAMethodsResponse(
        customer_id=methods.customer_id,
        methods=methods.methods,
        preferred=methods.preferred,
    )
