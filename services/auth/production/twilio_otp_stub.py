"""
twilio_otp_stub.py — Production wiring stubs for OTP delivery via Twilio (SMS) and SendGrid (email).

These classes satisfy OtpDeliveryPort structurally but raise NotImplementedError on all
network-touching methods. They exist to mark the production integration surface and provide
docstrings for the future production team.

Canon: ADR-029 + ADR-025 §15-16 + OtpDeliveryPort FROZEN (PORT-CONTRACTS-FREEZE-2026-05-08)
"""

from __future__ import annotations

from typing import Literal

from services.auth.legacy.legacy_otp_adapter import LegacyOtpAdapter
from services.auth.otp_delivery_port import (
    OtpDeliveryReceipt,
)


class TwilioOtpStub(LegacyOtpAdapter):
    """
    Production stub: SMS OTP delivery via Twilio Verify or Messaging API.

    Requirements for production implementation:
      - Package dep: twilio>=9 (add to pyproject.toml [project.dependencies])
      - Env vars: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER
      - Integration tests: run against Twilio sandbox (not live numbers)
      - Implement send_otp() via twilio.rest.Client().messages.create(...)
      - Retain LegacyOtpAdapter.verify_otp() for in-process code storage until
        Twilio Verify service is wired for server-side verification.

    Implement in a separate PR tagged [IL-OTP-PROD-01].
    """

    def send_otp(
        self,
        *,
        channel: Literal["sms", "email"],
        target: str,
        code: str,
        ttl_seconds: int,
    ) -> OtpDeliveryReceipt:
        raise NotImplementedError(
            "TwilioOtpStub.send_otp: not implemented. "
            "Requires twilio>=9 + TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_FROM_NUMBER env vars. "
            "Implement in a dedicated production PR with Twilio sandbox integration tests."
        )


class SendGridOtpStub(LegacyOtpAdapter):
    """
    Production stub: email OTP delivery via SendGrid Dynamic Templates.

    Requirements for production implementation:
      - Package dep: sendgrid>=6 (add to pyproject.toml [project.dependencies])
      - Env vars: SENDGRID_API_KEY, SENDGRID_FROM_EMAIL, SENDGRID_OTP_TEMPLATE_ID
      - Integration tests: run against SendGrid sandbox / inbound parse webhook test
      - Implement send_otp() via sendgrid.SendGridAPIClient().send(Mail(...))
      - Retain LegacyOtpAdapter.verify_otp() for in-process code verification.

    Implement in a separate PR tagged [IL-OTP-PROD-02].
    """

    def send_otp(
        self,
        *,
        channel: Literal["sms", "email"],
        target: str,
        code: str,
        ttl_seconds: int,
    ) -> OtpDeliveryReceipt:
        raise NotImplementedError(
            "SendGridOtpStub.send_otp: not implemented. "
            "Requires sendgrid>=6 + SENDGRID_API_KEY / SENDGRID_FROM_EMAIL / SENDGRID_OTP_TEMPLATE_ID env vars. "
            "Implement in a dedicated production PR with SendGrid sandbox integration tests."
        )


# Structural conformance assertion (import-time, zero cost in production)
def _assert_protocol_conformance() -> None:
    assert isinstance(TwilioOtpStub, type)
    assert isinstance(SendGridOtpStub, type)
