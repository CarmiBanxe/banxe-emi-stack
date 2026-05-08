"""
twilio_otp_adapter.py — Production OTP delivery via Twilio Verify v2.

Implements OtpDeliveryPort.send_otp via POST /v2/Services/{ServiceSid}/Verifications
with CustomCode (passes our pre-generated code to Twilio).
Implements OtpDeliveryPort.verify_otp via POST /v2/Services/{ServiceSid}/VerificationCheck
(Twilio validates server-side; single-use semantics enforced by Verify status=approved).
generate_otp and can_resend are inherited from LegacyOtpAdapter (in-memory, NIST SP 800-63B).

Env vars:
  TWILIO_ACCOUNT_SID      — Twilio account identifier
  TWILIO_AUTH_TOKEN       — Twilio account auth token
  TWILIO_VERIFY_SERVICE_SID — Twilio Verify Service SID (VA...)

Sandbox: use Twilio test credentials (AC test SID + test auth token) in CI.
No live numbers are dialled when test credentials are active.

Canon: ADR-029 + ADR-025 §15-16 + OtpDeliveryPort FROZEN (PORT-CONTRACTS-FREEZE-2026-05-08)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
import os
from typing import Literal

import httpx

from services.auth.legacy.legacy_otp_adapter import LegacyOtpAdapter
from services.auth.otp_delivery_port import OtpDeliveryReceipt, OtpVerifyResult

logger = logging.getLogger(__name__)

_TWILIO_BASE = "https://verify.twilio.com"


class TwilioOtpAdapter(LegacyOtpAdapter):
    """
    Production OTP adapter: SMS/email delivery via Twilio Verify v2.

    send_otp  → POST /v2/Services/{ServiceSid}/Verifications (CustomCode=code)
    verify_otp → POST /v2/Services/{ServiceSid}/VerificationCheck (server-side)
    generate_otp, can_resend — inherited in-memory implementation.

    The in-memory store from LegacyOtpAdapter is NOT used for verify_otp;
    Twilio holds the verification state.  can_resend uses the local store as
    a lightweight rate-limit gate before hitting the Twilio API.
    """

    def __init__(self, *, sandbox: bool = True) -> None:
        super().__init__()
        self._account_sid = os.environ["TWILIO_ACCOUNT_SID"]
        self._auth_token = os.environ["TWILIO_AUTH_TOKEN"]
        self._service_sid = os.environ["TWILIO_VERIFY_SERVICE_SID"]
        self._sandbox = sandbox
        self._http = httpx.Client(
            base_url=_TWILIO_BASE,
            auth=(self._account_sid, self._auth_token),
            timeout=10.0,
        )

    # ── OtpDeliveryPort overrides ─────────────────────────────────────────────

    def send_otp(
        self,
        *,
        channel: Literal["sms", "email"],
        target: str,
        code: str,
        ttl_seconds: int,
    ) -> OtpDeliveryReceipt:
        """
        Start a Twilio Verify v2 verification with a custom code.

        Twilio stores the code server-side; verify_otp checks against Twilio,
        not the local in-memory dict.
        """
        resp = self._http.post(
            f"/v2/Services/{self._service_sid}/Verifications",
            data={"To": target, "Channel": channel, "CustomCode": code},
        )
        resp.raise_for_status()
        body = resp.json()
        now = datetime.now(UTC)
        receipt = OtpDeliveryReceipt(
            delivery_id=body["sid"],
            channel=channel,
            target=target,
            sent_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
        )
        # mirror into in-memory store so can_resend works without extra API call
        super().send_otp(channel=channel, target=target, code=code, ttl_seconds=ttl_seconds)
        logger.info(
            "Twilio Verify OTP sent — channel=%s target=%s sid=%s",
            channel,
            target,
            body["sid"],
        )
        return receipt

    def verify_otp(
        self,
        *,
        channel: str,
        target: str,
        code: str,
    ) -> OtpVerifyResult:
        """
        Check OTP via Twilio VerificationCheck endpoint.

        status=approved → success; any other status → failure.
        404 from Twilio → OTP expired or never created.
        """
        resp = self._http.post(
            f"/v2/Services/{self._service_sid}/VerificationCheck",
            data={"To": target, "Code": code},
        )
        if resp.status_code == 404:
            return OtpVerifyResult(success=False, message="OTP not found or expired")
        resp.raise_for_status()
        body = resp.json()
        approved = body.get("status") == "approved"
        return OtpVerifyResult(
            success=approved,
            message="approved" if approved else body.get("status", "failed"),
            delivery_id=body.get("sid"),
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> TwilioOtpAdapter:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
