"""
legacy_totp_adapter.py — LegacyTotpAdapter implements TwoFactorPort via pyotp (RFC-6238).

Semantic rewrite of GrpcTFAConnector (banxe-common/lib/.../2fa-connector.service.ts).
gRPC transport (BaseConnectorGrpcService / banxe-2fa microservice) dropped — not
portable to EMI Python stack.  TOTP computed locally via pyotp; zero network deps.

Upstream gRPC method → TwoFactorPort mapping:
  generateTOTP + enable2FA(type=OTP)    → setup_totp()
  confirmEnabling2FA()                  → confirm_totp()
  getEnabled2FA()                       → is_enabled()
  verify2FAToken(type=OTP)              → verify_totp()       RFC-6238 ±1 clock-skew
  getRecoveryCode + confirmOneTimeCode  → verify_backup_code() one-time, case-insensitive
  disable2FA + confirmDisabling2FA      → revoke_totp()
  [internal state]                      → backup_codes_remaining()

  OUT OF SCOPE (separate concerns, not mapped):
    send2FAToken / generateOneTimeCode / checkResendOneTimeCode → OtpDeliveryPort (REWRITE-1)
    create2FAOperationId / get2FAOperationId  → stateless in EMI adapter
    verifyCaptchaToken                        → separate captcha concern

Canon: ADR-015 + ADR-025 §15-16 + AUTH_IMPORT_ORDER
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import hmac
import logging
import os
import secrets
import time
from typing import Protocol

try:
    import pyotp  # type: ignore[import]
except ImportError as exc:  # pragma: no cover
    raise ImportError("pyotp required: pip install pyotp") from exc

from services.auth.two_factor import TOTPSetup, VerifyResult

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

_ISSUER = os.environ.get("TOTP_ISSUER", "Banxe")
_DIGITS = 6
_INTERVAL = 30
_VALID_WINDOW = 1  # RFC-6238 §5.2 — allow ±1 time-step for clock drift
_BACKUP_COUNT = 8
_BACKUP_HEX_BYTES = 4  # secrets.token_hex(4) → 8-char uppercase hex code
_MAX_ATTEMPTS = 5
_ATTEMPT_WINDOW_SEC = _INTERVAL


# ── Error ─────────────────────────────────────────────────────────────────────


class TotpAdapterError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# ── TotpStorePort ─────────────────────────────────────────────────────────────


class TotpStorePort(Protocol):
    """Storage backend injected into LegacyTotpAdapter (Redis/DB in production)."""

    def save_secret(self, customer_id: str, secret: str) -> None: ...
    def get_secret(self, customer_id: str) -> str | None: ...
    def set_enabled(self, customer_id: str, enabled: bool) -> None: ...
    def get_enabled(self, customer_id: str) -> bool: ...
    def save_backup_hashes(self, customer_id: str, hashes: list[str]) -> None: ...
    def get_backup_hashes(self, customer_id: str) -> list[str]: ...
    def remove_customer(self, customer_id: str) -> None: ...
    def record_attempt(self, customer_id: str, ts: float) -> None: ...
    def get_attempts(self, customer_id: str) -> list[float]: ...
    def clear_attempts(self, customer_id: str) -> None: ...


# ── InMemoryTotpStore ─────────────────────────────────────────────────────────


class InMemoryTotpStore:
    """Dict-backed default store — sufficient for tests and single-process dev."""

    def __init__(self) -> None:
        self._secrets: dict[str, str] = {}
        self._enabled: dict[str, bool] = {}
        self._backup_hashes: dict[str, list[str]] = {}
        self._attempts: dict[str, list[float]] = {}

    def save_secret(self, customer_id: str, secret: str) -> None:
        self._secrets[customer_id] = secret

    def get_secret(self, customer_id: str) -> str | None:
        return self._secrets.get(customer_id)

    def set_enabled(self, customer_id: str, enabled: bool) -> None:
        self._enabled[customer_id] = enabled

    def get_enabled(self, customer_id: str) -> bool:
        return self._enabled.get(customer_id, False)

    def save_backup_hashes(self, customer_id: str, hashes: list[str]) -> None:
        self._backup_hashes[customer_id] = list(hashes)

    def get_backup_hashes(self, customer_id: str) -> list[str]:
        return list(self._backup_hashes.get(customer_id, []))

    def remove_customer(self, customer_id: str) -> None:
        self._secrets.pop(customer_id, None)
        self._enabled.pop(customer_id, None)
        self._backup_hashes.pop(customer_id, None)
        self._attempts.pop(customer_id, None)

    def record_attempt(self, customer_id: str, ts: float) -> None:
        self._attempts.setdefault(customer_id, []).append(ts)

    def get_attempts(self, customer_id: str) -> list[float]:
        return list(self._attempts.get(customer_id, []))

    def clear_attempts(self, customer_id: str) -> None:
        self._attempts.pop(customer_id, None)


# ── LegacyTotpAdapter ─────────────────────────────────────────────────────────


class LegacyTotpAdapter:
    """
    TwoFactorPort implementation — semantic rewrite of GrpcTFAConnector.
    Backed by pyotp (RFC-6238, 30 s step, 6 digits) and an injected TotpStorePort.
    """

    def __init__(self, store: TotpStorePort | None = None) -> None:
        self._store: TotpStorePort = store if store is not None else InMemoryTotpStore()

    # ── TwoFactorPort ─────────────────────────────────────────────────────────

    def setup_totp(self, customer_id: str, account_name: str | None = None) -> TOTPSetup:
        """generateTOTP + enable2FA(OTP): new secret, provisioning URI, backup codes."""
        secret = pyotp.random_base32()
        label = account_name or customer_id
        totp = pyotp.TOTP(secret, issuer=_ISSUER, digits=_DIGITS, interval=_INTERVAL)
        uri = totp.provisioning_uri(name=label, issuer_name=_ISSUER)

        raw = [secrets.token_hex(_BACKUP_HEX_BYTES).upper() for _ in range(_BACKUP_COUNT)]
        hashes = [_hash_backup(secret, code) for code in raw]

        self._store.save_secret(customer_id, secret)
        self._store.save_backup_hashes(customer_id, hashes)
        self._store.set_enabled(customer_id, False)  # pending confirm
        self._store.clear_attempts(customer_id)

        logger.info("TOTP setup initiated — customer %s", customer_id)
        return TOTPSetup(
            customer_id=customer_id,
            secret=secret,
            provisioning_uri=uri,
            backup_codes=raw,
            created_at=datetime.now(UTC),
        )

    def confirm_totp(self, customer_id: str, otp: str) -> bool:
        """confirmEnabling2FA: activate TOTP after customer scans and verifies first OTP."""
        if not _raw_verify(self._store.get_secret(customer_id), otp):
            return False
        self._store.set_enabled(customer_id, True)
        logger.info("TOTP confirmed — customer %s", customer_id)
        return True

    def is_enabled(self, customer_id: str) -> bool:
        """getEnabled2FA: True if OTP type is active (confirmed) for this customer."""
        return self._store.get_enabled(customer_id)

    def verify_totp(self, customer_id: str, otp: str) -> VerifyResult:
        """verify2FAToken(type=OTP): rate-limited verify with RFC-6238 ±1 clock-skew."""
        if not self._store.get_enabled(customer_id):
            return VerifyResult(success=False, message="TOTP not enabled")

        if self._rate_limited(customer_id):
            return VerifyResult(success=False, message="Too many attempts", attempts_remaining=0)

        self._store.record_attempt(customer_id, time.monotonic())

        if _raw_verify(self._store.get_secret(customer_id), otp):
            self._store.clear_attempts(customer_id)
            return VerifyResult(success=True, message="OTP verified")

        remaining = max(0, _MAX_ATTEMPTS - len(self._recent_attempts(customer_id)))
        return VerifyResult(success=False, message="Invalid OTP", attempts_remaining=remaining)

    def verify_backup_code(self, customer_id: str, code: str) -> VerifyResult:
        """confirmOneTimeCode: consume one backup code (one-time use, case-insensitive)."""
        secret = self._store.get_secret(customer_id)
        if not secret:
            return VerifyResult(success=False, message="TOTP not set up")

        normalised = (code or "").upper().strip()
        if not normalised:
            return VerifyResult(success=False, message="Empty backup code")

        target = _hash_backup(secret, normalised)
        hashes = self._store.get_backup_hashes(customer_id)
        if target not in hashes:
            return VerifyResult(success=False, message="Invalid backup code")

        hashes.remove(target)
        self._store.save_backup_hashes(customer_id, hashes)
        remaining = len(hashes)
        logger.warning("Backup code consumed — customer %s, %d remaining", customer_id, remaining)
        return VerifyResult(success=True, message=f"Backup code accepted. {remaining} remaining.")

    def revoke_totp(self, customer_id: str) -> None:
        """disable2FA + confirmDisabling2FA: clear all TOTP state for the customer."""
        self._store.remove_customer(customer_id)
        logger.info("TOTP revoked — customer %s", customer_id)

    def backup_codes_remaining(self, customer_id: str) -> int:
        """Return count of unconsumed backup code hashes."""
        return len(self._store.get_backup_hashes(customer_id))

    # ── Internals ─────────────────────────────────────────────────────────────

    def _recent_attempts(self, customer_id: str) -> list[float]:
        now = time.monotonic()
        return [t for t in self._store.get_attempts(customer_id) if now - t < _ATTEMPT_WINDOW_SEC]

    def _rate_limited(self, customer_id: str) -> bool:
        return len(self._recent_attempts(customer_id)) >= _MAX_ATTEMPTS


# ── Module-level helpers ──────────────────────────────────────────────────────


def _raw_verify(secret: str | None, otp: str | None) -> bool:
    """Stateless pyotp verify; valid_window=1 allows ±1 time-step clock drift."""
    if not secret or not otp or not otp.strip():
        return False
    totp = pyotp.TOTP(secret, digits=_DIGITS, interval=_INTERVAL)
    return bool(totp.verify(otp.strip(), valid_window=_VALID_WINDOW))


def _hash_backup(secret: str, code: str) -> str:
    """HMAC-SHA256(secret, code) for one-way backup code storage."""
    return hmac.new(secret.encode(), code.encode(), hashlib.sha256).hexdigest()
