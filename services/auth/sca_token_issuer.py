"""
services/auth/sca_token_issuer.py — JWT-based SCA token issuer
S15-01 / Sprint 4 Track A | banxe-emi-stack

Implements ScaTokenIssuerPort. Centralises the only remaining jwt.encode
call inside the SCA contour — sca_service.py no longer touches jwt directly.

PSD2 RTS Art.10 dynamic linking claims:
    sub      — customer_id
    txn_id   — transaction_id
    amount   — transaction amount (optional)
    payee    — payee name (optional)
    method   — "otp" | "biometric"
    sca      — True
    iat / exp
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import os

import jwt

from services.auth.sca_models import SCAChallenge

SCA_TOKEN_TTL_SEC = int(os.environ.get("SCA_TOKEN_TTL_SEC", "300"))
SCA_SECRET_KEY = os.environ.get("SCA_SECRET_KEY", "dev-sca-secret-change-in-prod")
SCA_ALGORITHM = "HS256"


class JwtScaTokenIssuer:
    """JWT issuer for SCA dynamic-linking tokens."""

    def __init__(
        self,
        secret_key: str = SCA_SECRET_KEY,
        algorithm: str = SCA_ALGORITHM,
        ttl_sec: int = SCA_TOKEN_TTL_SEC,
    ) -> None:
        self._secret = secret_key
        self._algorithm = algorithm
        self._ttl_sec = ttl_sec

    def issue(self, challenge: SCAChallenge) -> str:
        now = datetime.now(tz=UTC)
        expires_at = now + timedelta(seconds=self._ttl_sec)
        payload: dict = {
            "sub": challenge.customer_id,
            "txn_id": challenge.transaction_id,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
            "sca": True,
            "method": challenge.method,
        }
        if challenge.amount:
            payload["amount"] = challenge.amount
        if challenge.payee:
            payload["payee"] = challenge.payee
        return jwt.encode(payload, self._secret, algorithm=self._algorithm)
