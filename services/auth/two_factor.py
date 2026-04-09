"""
two_factor.py — Lightweight 2FA (TOTP + Backup Codes)
S17-04: 2FA/MFA — RFC 6238 TOTP, PSR 2017 Reg.71 (SCA), FCA SM&CR
Pattern: Geniusto v5 "2FA process + 2FA service"

WHY THIS FILE EXISTS
--------------------
FCA PSR 2017 Reg.71 requires Strong Customer Authentication (SCA) for:
  - Account login from new device
  - Payments >£30
  - Sensitive profile changes

Keycloak (FA-14, IL-029) handles session management and will be the
production IAM. This module provides lightweight TOTP 2FA that can work
standalone (no Keycloak dependency) using pyotp.

Integrates with:
  - Notification service: OTP SMS/email delivery
  - IAM port: session validation
  - Payment service: >£30 auth gate (PSR 2017 Reg.71)
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────

TOTP_ISSUER = os.environ.get("TOTP_ISSUER", "Banxe")
TOTP_DIGITS = 6
TOTP_INTERVAL = 30  # seconds (RFC 6238 default)
TOTP_VALID_WINDOW = 1  # allow ±1 interval for clock drift
BACKUP_CODE_COUNT = 8
BACKUP_CODE_LENGTH = 8  # hex chars
MAX_VERIFY_ATTEMPTS = 5  # rate limit per window


# ── Domain types ───────────────────────────────────────────────────────────────


@dataclass
class TOTPSetup:
    """Returned when enabling TOTP for a user."""

    customer_id: str
    secret: str  # Base32 secret (store encrypted)
    provisioning_uri: str  # otpauth:// URI for QR code
    backup_codes: list[str]  # One-time use emergency codes
    created_at: datetime


@dataclass
class VerifyResult:
    success: bool
    message: str
    attempts_remaining: int | None = None


# ── TOTP service ───────────────────────────────────────────────────────────────


class TOTPService:
    """
    RFC 6238 TOTP — Time-based One-Time Password.

    Uses pyotp for TOTP generation/verification.
    Backup codes: HMAC-SHA256 of (secret + code) stored as hashes.
    Rate limiting: per-user attempt counter with TTL.

    Example:
        svc = TOTPService()
        setup = svc.setup_totp("cust-001")
        # Customer scans QR code with Google Authenticator
        result = svc.verify_totp("cust-001", user_entered_otp)
    """

    def __init__(self) -> None:
        # In-memory stores — replace with Redis/PostgreSQL in production
        self._secrets: dict[str, str] = {}  # customer_id → base32 secret
        self._backup_hashes: dict[str, list[str]] = {}  # customer_id → [hashed_codes]
        self._attempts: dict[str, list[float]] = {}  # customer_id → [timestamps]
        self._enabled: dict[str, bool] = {}

    def setup_totp(self, customer_id: str, account_name: str | None = None) -> TOTPSetup:
        """
        Generate a new TOTP secret for a customer.
        Returns provisioning_uri for QR code display + backup codes.
        """
        try:
            import pyotp  # type: ignore[import]
        except ImportError:
            raise ImportError("Install pyotp: pip install pyotp")

        secret = pyotp.random_base32()
        totp = pyotp.TOTP(secret, issuer=TOTP_ISSUER, digits=TOTP_DIGITS, interval=TOTP_INTERVAL)

        label = account_name or customer_id
        uri = totp.provisioning_uri(name=label, issuer_name=TOTP_ISSUER)

        # Generate backup codes
        raw_codes = [
            secrets.token_hex(BACKUP_CODE_LENGTH // 2).upper() for _ in range(BACKUP_CODE_COUNT)
        ]
        hashed = [self._hash_code(secret, code) for code in raw_codes]

        self._secrets[customer_id] = secret
        self._backup_hashes[customer_id] = hashed
        self._enabled[customer_id] = False  # Requires confirmation before activation

        logger.info("TOTP setup initiated for customer: %s", customer_id)

        return TOTPSetup(
            customer_id=customer_id,
            secret=secret,
            provisioning_uri=uri,
            backup_codes=raw_codes,
            created_at=datetime.now(UTC),
        )

    def confirm_totp(self, customer_id: str, otp: str) -> bool:
        """Activate TOTP after customer confirms first OTP from authenticator."""
        result = self._do_verify_totp(customer_id, otp)
        if result:
            self._enabled[customer_id] = True
            logger.info("TOTP activated for customer: %s", customer_id)
        return result

    def is_enabled(self, customer_id: str) -> bool:
        return self._enabled.get(customer_id, False)

    def verify_totp(self, customer_id: str, otp: str) -> VerifyResult:
        """
        Verify TOTP OTP with rate limiting.
        PSR 2017 Reg.71: SCA must be resistant to brute force.
        """
        if not self._enabled.get(customer_id, False):
            return VerifyResult(success=False, message="2FA not enabled for this customer")

        if self._is_rate_limited(customer_id):
            return VerifyResult(
                success=False,
                message="Too many attempts. Try again in 30 seconds.",
                attempts_remaining=0,
            )

        self._record_attempt(customer_id)
        success = self._do_verify_totp(customer_id, otp)

        if success:
            self._clear_attempts(customer_id)
            return VerifyResult(success=True, message="OTP verified")

        remaining = MAX_VERIFY_ATTEMPTS - len(self._attempts.get(customer_id, []))
        return VerifyResult(
            success=False,
            message="Invalid OTP",
            attempts_remaining=max(0, remaining),
        )

    def verify_backup_code(self, customer_id: str, code: str) -> VerifyResult:
        """
        Verify and consume a backup code (one-time use).
        Used when customer lost authenticator device.
        """
        hashes = self._backup_hashes.get(customer_id, [])
        secret = self._secrets.get(customer_id, "")
        code_upper = code.upper().strip()
        code_hash = self._hash_code(secret, code_upper)

        if code_hash in hashes:
            hashes.remove(code_hash)  # Consume — one-time use
            self._backup_hashes[customer_id] = hashes
            logger.warning(
                "Backup code used for customer %s — %d remaining",
                customer_id,
                len(hashes),
            )
            return VerifyResult(
                success=True,
                message=f"Backup code accepted. {len(hashes)} backup codes remaining.",
            )
        return VerifyResult(success=False, message="Invalid backup code")

    def revoke_totp(self, customer_id: str) -> None:
        """Disable TOTP (e.g. customer lost device, re-setup required)."""
        self._secrets.pop(customer_id, None)
        self._backup_hashes.pop(customer_id, None)
        self._enabled.pop(customer_id, None)
        self._attempts.pop(customer_id, None)
        logger.info("TOTP revoked for customer: %s", customer_id)

    def backup_codes_remaining(self, customer_id: str) -> int:
        return len(self._backup_hashes.get(customer_id, []))

    # ── Internals ─────────────────────────────────────────────────────────────

    def _do_verify_totp(self, customer_id: str, otp: str) -> bool:
        try:
            import pyotp
        except ImportError:
            return False

        secret = self._secrets.get(customer_id)
        if not secret:
            return False
        totp = pyotp.TOTP(secret, digits=TOTP_DIGITS, interval=TOTP_INTERVAL)
        return totp.verify(otp.strip(), valid_window=TOTP_VALID_WINDOW)

    def _hash_code(self, secret: str, code: str) -> str:
        return hmac.new(secret.encode(), code.encode(), hashlib.sha256).hexdigest()

    def _is_rate_limited(self, customer_id: str) -> bool:
        now = time.monotonic()
        window = TOTP_INTERVAL
        recent = [t for t in self._attempts.get(customer_id, []) if now - t < window]
        self._attempts[customer_id] = recent
        return len(recent) >= MAX_VERIFY_ATTEMPTS

    def _record_attempt(self, customer_id: str) -> None:
        self._attempts.setdefault(customer_id, []).append(time.monotonic())

    def _clear_attempts(self, customer_id: str) -> None:
        self._attempts.pop(customer_id, None)
