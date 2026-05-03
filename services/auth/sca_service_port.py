"""ScaServicePort — hexagonal port for PSD2 SCA challenge lifecycle."""

from __future__ import annotations

from typing import Protocol

from services.auth.sca_models import SCAChallenge, SCAVerifyResult


class ScaServicePort(Protocol):
    def create_challenge(
        self,
        customer_id: str,
        transaction_id: str,
        method: str,
        amount: str | None = None,
        payee: str | None = None,
    ) -> SCAChallenge: ...

    def verify(
        self,
        challenge_id: str,
        otp_code: str | None = None,
        biometric_proof: str | None = None,
    ) -> SCAVerifyResult: ...

    def resend_challenge(self, challenge_id: str) -> SCAChallenge: ...
