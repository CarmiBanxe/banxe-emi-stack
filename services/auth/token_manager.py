"""
services/auth/token_manager.py — Token lifecycle manager
S15-FIX | PSD2 RTS Art.11 | banxe-emi-stack

Centralises JWT token issue / validate / refresh / inactivity-check.

PSD2 RTS Art.11: PSP must terminate session after ≤5 min inactivity.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
import os
import uuid

import jwt

logger = logging.getLogger("banxe.auth.token_manager")

# ── Config (mirrors api/routers/auth.py constants) ────────────────────────────

_SECRET_KEY = os.environ.get("AUTH_SECRET_KEY", "dev-insecure-secret-change-in-prod")
_TTL_HOURS = int(os.environ.get("AUTH_TOKEN_TTL_HOURS", "24"))
_REFRESH_TTL_DAYS = int(os.environ.get("AUTH_REFRESH_TOKEN_TTL_DAYS", "7"))
_ALGORITHM = "HS256"

# PSD2 RTS Art.11: inactivity timeout ≤ 5 minutes (300 seconds)
PSD2_INACTIVITY_LIMIT_SEC = int(os.environ.get("PSD2_INACTIVITY_LIMIT_SEC", "300"))


class TokenValidationError(Exception):
    """Raised when token validation fails."""

    def __init__(self, message: str, code: str = "invalid_token") -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class TokenManager:
    """
    Manages JWT token lifecycle for Banxe auth.

    Responsibilities:
    - Issue access tokens (HS256, configurable TTL)
    - Issue refresh tokens (rotation, unique jti per token)
    - Validate access / refresh tokens
    - Check PSD2 RTS Art.11 inactivity timeout

    Protocol DI: inject secret_key / ttl for tests.
    """

    def __init__(
        self,
        secret_key: str = _SECRET_KEY,
        ttl_hours: int = _TTL_HOURS,
        refresh_ttl_days: int = _REFRESH_TTL_DAYS,
        inactivity_limit_sec: int = PSD2_INACTIVITY_LIMIT_SEC,
        algorithm: str = _ALGORITHM,
    ) -> None:
        self._secret = secret_key
        self._ttl_hours = ttl_hours
        self._refresh_ttl_days = refresh_ttl_days
        self._inactivity_sec = inactivity_limit_sec
        self._algorithm = algorithm

    # ── Token issuance ────────────────────────────────────────────────────────

    def issue_access_token(
        self, customer_id: str, email: str | None = None
    ) -> tuple[str, datetime]:
        """Issue a new access token with optional email claim."""
        now = datetime.now(tz=UTC)
        expires_at = now + timedelta(hours=self._ttl_hours)
        payload: dict = {
            "sub": customer_id,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }
        if email is not None:
            payload["email"] = email
        token = jwt.encode(payload, self._secret, algorithm=self._algorithm)
        logger.debug("token_manager.access_token_issued customer=%s", customer_id)
        return token, expires_at

    def issue_refresh_token(self, customer_id: str) -> tuple[str, datetime]:
        """
        Issue a new refresh token with unique jti.
        Unique jti ensures each rotation produces a distinct token (replay prevention).

        Returns:
            (encoded_jwt, expires_at)
        """
        now = datetime.now(tz=UTC)
        expires_at = now + timedelta(days=self._refresh_ttl_days)
        payload = {
            "sub": customer_id,
            "type": "refresh",
            "jti": str(uuid.uuid4()),  # unique per token — rotation detection
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }
        token = jwt.encode(payload, self._secret, algorithm=self._algorithm)
        logger.debug("token_manager.refresh_token_issued customer=%s", customer_id)
        return token, expires_at

    # ── Token validation ──────────────────────────────────────────────────────

    def validate_access_token(self, token: str) -> dict:
        """
        Decode and validate an access token.

        Returns:
            Decoded payload dict.

        Raises:
            TokenValidationError: if token is expired, invalid, or wrong type.
        """
        try:
            payload = jwt.decode(token, self._secret, algorithms=[self._algorithm])
        except jwt.ExpiredSignatureError:
            raise TokenValidationError("Access token expired", code="token_expired")
        except jwt.InvalidTokenError as exc:
            raise TokenValidationError(f"Invalid access token: {exc}", code="invalid_token")

        if payload.get("type") == "refresh":
            raise TokenValidationError(
                "Expected access token, got refresh token", code="wrong_type"
            )
        if not payload.get("sub"):
            raise TokenValidationError("Token missing subject claim", code="missing_sub")
        return payload

    def validate_refresh_token(self, token: str) -> dict:
        """
        Decode and validate a refresh token.

        Returns:
            Decoded payload dict.

        Raises:
            TokenValidationError: if token is expired, invalid, or not a refresh token.
        """
        try:
            payload = jwt.decode(token, self._secret, algorithms=[self._algorithm])
        except jwt.ExpiredSignatureError:
            raise TokenValidationError("Refresh token expired", code="token_expired")
        except jwt.InvalidTokenError as exc:
            raise TokenValidationError(f"Invalid refresh token: {exc}", code="invalid_token")

        if payload.get("type") != "refresh":
            raise TokenValidationError("Token is not a refresh token", code="wrong_type")
        if not payload.get("sub"):
            raise TokenValidationError("Refresh token missing subject claim", code="missing_sub")
        if not payload.get("jti"):
            raise TokenValidationError("Refresh token missing jti claim", code="missing_jti")
        return payload

    # ── Inactivity check (PSD2 RTS Art.11) ───────────────────────────────────

    def is_inactive(self, last_activity: datetime) -> bool:
        """
        Return True if the session has been inactive beyond PSD2_INACTIVITY_LIMIT_SEC.

        PSD2 RTS Art.11: PSP must terminate PSU session after ≤5 min inactivity.
        """
        now = datetime.now(tz=UTC)
        if last_activity.tzinfo is None:
            last_activity = last_activity.replace(tzinfo=UTC)
        elapsed = (now - last_activity).total_seconds()
        return elapsed > self._inactivity_sec

    # ── Rotation cycle ────────────────────────────────────────────────────────

    def rotate(self, refresh_token: str) -> tuple[str, str, datetime, datetime]:
        """
        Validate refresh token and issue a new token pair (rotation).

        Returns:
            (new_access_token, new_refresh_token, access_expires_at, refresh_expires_at)

        Raises:
            TokenValidationError: if the refresh token is invalid.
        """
        payload = self.validate_refresh_token(refresh_token)
        customer_id = payload["sub"]
        access_token, access_exp = self.issue_access_token(customer_id)
        new_refresh, refresh_exp = self.issue_refresh_token(customer_id)
        logger.info("token_manager.rotated customer=%s", customer_id)
        return access_token, new_refresh, access_exp, refresh_exp
