"""
otp_delivery_port.py — OtpDeliveryPort Protocol + domain models.

Hexagonal port contract for OTP generation, delivery, verification, and resend-rate-check.

Upstream semantic scope: CodeService (banxe-common/code.service.ts).
  randomString(5) + codeRepository.save() → generate_otp() + send_otp()
  sendCode(type, destination)             → send_otp()
  checkCode(codeId, code)                 → verify_otp()
  retryDelay placeholder                  → can_resend()

OUT OF SCOPE (infrastructure, separate adapters):
  createApolloClient / registerDevice / notification gRPC → NotificationPort
  addCredentials after verify → AuthApplicationService concern

Canon: ADR-029 + ADR-015 + ADR-025 §15-16 + AUTH_IMPORT_ORDER
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel


class OtpDeliveryReceipt(BaseModel, frozen=True):
    """Confirmation that an OTP was registered for delivery to a channel/target."""

    delivery_id: str
    channel: str
    target: str
    sent_at: datetime
    expires_at: datetime


class OtpVerifyResult(BaseModel, frozen=True):
    """Result of an OTP verification attempt."""

    success: bool
    message: str
    delivery_id: str | None = None


class ResendCheck(BaseModel, frozen=True):
    """Rate-limit gate for OTP resend requests."""

    can_resend: bool
    seconds_remaining: int  # 0 when can_resend is True
    last_sent_at: datetime | None = None


@runtime_checkable
class OtpDeliveryPort(Protocol):
    """
    Port contract for OTP lifecycle: generate → send → verify + resend-rate-check.

    Implementations:
      LegacyOtpAdapter  — in-memory backend (dev/test, REWRITE-1)
      TwilioOtpAdapter  — SMS via Twilio (future production adapter)
      SendGridOtpAdapter — email via SendGrid (future production adapter)
    """

    def generate_otp(self, *, length: int = 6, alphabet: str = "digits") -> str:
        """
        Generate a cryptographically secure OTP code.
        alphabet: 'digits' (0-9) or 'alphanumeric' (A-Z0-9).
        """
        ...

    def send_otp(
        self,
        *,
        channel: Literal["sms", "email"],
        target: str,
        code: str,
        ttl_seconds: int,
    ) -> OtpDeliveryReceipt:
        """
        Register a pending OTP for (channel, target) with TTL.
        Legacy adapter stores in memory; production adapters dispatch via SMS/email.
        """
        ...

    def verify_otp(
        self,
        *,
        channel: str,
        target: str,
        code: str,
    ) -> OtpVerifyResult:
        """Verify OTP against the latest active pending record for (channel, target)."""
        ...

    def can_resend(
        self,
        *,
        channel: str,
        target: str,
        min_interval_seconds: int,
    ) -> ResendCheck:
        """Rate-limit check: True if last send was ≥ min_interval_seconds ago (or never sent)."""
        ...
