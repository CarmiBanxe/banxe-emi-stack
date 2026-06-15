"""
legacy_otp_adapter.py — LegacyOtpAdapter implements OtpDeliveryPort (in-memory, REWRITE-1).

Semantic rewrite of CodeService (banxe-common/code.service.ts).
gRPC notification transport dropped — not portable to EMI Python stack.
OTP generation uses secrets.choice (NIST SP 800-63B compliant); zero network deps.

Upstream TS method → OtpDeliveryPort mapping:
  randomString(5) + codeRepository.save()  → generate_otp() + send_otp()
  sendCode(type, destination)              → send_otp()
  checkCode(codeId, code)                  → verify_otp()
  retryDelay placeholder                   → can_resend()

OUT OF SCOPE (separate concerns, not mapped):
  createApolloClient / registerDevice / gRPC notification → NotificationPort
  addCredentials after verify              → AuthApplicationService concern
  TOTP (generate2FAToken / verify2FAToken) → TwoFactorPort (ADR-015, Wave B Step 1)

Canon: ADR-029 + ADR-015 + ADR-025 §15-16 + AUTH_IMPORT_ORDER
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hmac
import logging
import secrets
import string
from typing import Literal

from services.auth.otp_delivery_port import (
    OtpDeliveryPort,  # noqa: F401 — referenced in class docstring
    OtpDeliveryReceipt,
    OtpVerifyResult,
    ResendCheck,
)

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

_DIGIT_ALPHABET: str = string.digits
_ALPHANUMERIC_ALPHABET: str = string.ascii_uppercase + string.digits
_DEFAULT_LENGTH: int = 6
_DEFAULT_TTL_SECONDS: int = 300

# ── Internal record ───────────────────────────────────────────────────────────


@dataclass
class _OtpRecord:
    """Internal store entry: keyed by (channel, target), replaced on each send_otp."""

    delivery_id: str
    channel: str
    target: str
    code: str
    sent_at: datetime
    expires_at: datetime


# ── LegacyOtpAdapter ─────────────────────────────────────────────────────────


class LegacyOtpAdapter:
    """
    OtpDeliveryPort implementation — semantic rewrite of CodeService (REWRITE-1).

    In-memory dict keyed by (channel, target). Not durable across process restarts;
    acceptable for dev/test. Redis adapter (Wave C) handles durability.

    Not concurrency-safe under multiple ASGI workers — use Redis adapter in production.
    """

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], _OtpRecord] = {}

    # ── OtpDeliveryPort ───────────────────────────────────────────────────────

    def generate_otp(self, *, length: int = _DEFAULT_LENGTH, alphabet: str = "digits") -> str:
        """
        Generate a cryptographically secure OTP code.
        alphabet: 'digits' (0-9) or 'alphanumeric' (A-Z0-9).
        """
        pool = _ALPHANUMERIC_ALPHABET if alphabet == "alphanumeric" else _DIGIT_ALPHABET
        return "".join(secrets.choice(pool) for _ in range(length))

    def send_otp(
        self,
        *,
        channel: Literal["sms", "email"],
        target: str,
        code: str,
        ttl_seconds: int,
    ) -> OtpDeliveryReceipt:
        """
        Register a pending OTP for (channel, target).
        Replaces any previous record for the same (channel, target) pair.
        Channel is stored for routing context; no network call is made.
        """
        delivery_id = secrets.token_urlsafe(16)
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=ttl_seconds)
        self._records[(channel, target)] = _OtpRecord(
            delivery_id=delivery_id,
            channel=channel,
            target=target,
            code=code,
            sent_at=now,
            expires_at=expires_at,
        )
        logger.info(
            "OTP registered — channel=%s target=%s delivery_id=%s", channel, target, delivery_id
        )
        return OtpDeliveryReceipt(
            delivery_id=delivery_id,
            channel=channel,
            target=target,
            sent_at=now,
            expires_at=expires_at,
        )

    def verify_otp(
        self,
        *,
        channel: str,
        target: str,
        code: str,
    ) -> OtpVerifyResult:
        """
        Verify OTP against the active record for (channel, target).
        OTP is consumed on success to prevent replay attacks.
        """
        record = self._records.get((channel, target))
        if record is None:
            return OtpVerifyResult(success=False, message="No pending OTP found")

        if datetime.now(UTC) > record.expires_at:
            return OtpVerifyResult(success=False, message="OTP expired")

        # constant-time comparison prevents timing attacks
        if not hmac.compare_digest(record.code, code):
            return OtpVerifyResult(success=False, message="Invalid code")

        # consume on success — single-use semantics
        del self._records[(channel, target)]
        logger.info("OTP verified — delivery_id=%s", record.delivery_id)
        return OtpVerifyResult(success=True, message="OTP verified", delivery_id=record.delivery_id)

    def can_resend(
        self,
        *,
        channel: str,
        target: str,
        min_interval_seconds: int,
    ) -> ResendCheck:
        """
        Rate-limit gate: True if last send was ≥ min_interval_seconds ago (or never sent).
        Does not consume or alter the pending record.
        """
        record = self._records.get((channel, target))
        if record is None:
            return ResendCheck(can_resend=True, seconds_remaining=0, last_sent_at=None)

        elapsed = (datetime.now(UTC) - record.sent_at).total_seconds()
        if elapsed >= min_interval_seconds:
            return ResendCheck(can_resend=True, seconds_remaining=0, last_sent_at=record.sent_at)

        remaining = max(0, int(min_interval_seconds - elapsed))
        return ResendCheck(
            can_resend=False, seconds_remaining=remaining, last_sent_at=record.sent_at
        )
