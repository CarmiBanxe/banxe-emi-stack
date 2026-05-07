"""In-memory OtpDeliveryPort fake — satisfies the full Protocol contract.

Used by LegacyScaAdapter tests so that SCA challenge tests remain deterministic
and free of secrets.choice entropy.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from services.auth.otp_delivery_port import (
    OtpDeliveryPort,
    OtpDeliveryReceipt,
    OtpVerifyResult,
    ResendCheck,
)


class FakeOtpAdapter:
    """Programmable in-memory adapter implementing OtpDeliveryPort.

    Constructor knobs:
        verify_success  — controls whether verify_otp returns success
        generated_code  — fixed code returned by generate_otp (default "123456")
    """

    def __init__(
        self,
        *,
        verify_success: bool = True,
        generated_code: str = "123456",
        can_resend_result: bool = True,
    ) -> None:
        self._verify_success = verify_success
        self._generated_code = generated_code
        self._can_resend_result = can_resend_result
        self.send_calls: list[dict[str, object]] = []
        self.verify_calls: list[dict[str, object]] = []
        self.can_resend_calls: list[dict[str, object]] = []
        self._last_delivery_id: str = "fake-delivery-id"

    # ── OtpDeliveryPort ───────────────────────────────────────────────────────

    def generate_otp(self, *, length: int = 6, alphabet: str = "digits") -> str:
        return (
            self._generated_code[:length]
            if len(self._generated_code) >= length
            else self._generated_code
        )

    def send_otp(
        self,
        *,
        channel: str,
        target: str,
        code: str,
        ttl_seconds: int,
    ) -> OtpDeliveryReceipt:
        self.send_calls.append(
            {"channel": channel, "target": target, "code": code, "ttl_seconds": ttl_seconds}
        )
        now = datetime.now(UTC)
        return OtpDeliveryReceipt(
            delivery_id=self._last_delivery_id,
            channel=channel,
            target=target,
            sent_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
        )

    def verify_otp(
        self,
        *,
        channel: str,
        target: str,
        code: str,
    ) -> OtpVerifyResult:
        self.verify_calls.append({"channel": channel, "target": target, "code": code})
        if self._verify_success:
            return OtpVerifyResult(
                success=True, message="OTP verified", delivery_id=self._last_delivery_id
            )
        return OtpVerifyResult(success=False, message="Invalid code")

    def can_resend(
        self,
        *,
        channel: str,
        target: str,
        min_interval_seconds: int,
    ) -> ResendCheck:
        self.can_resend_calls.append(
            {"channel": channel, "target": target, "min_interval_seconds": min_interval_seconds}
        )
        return ResendCheck(can_resend=self._can_resend_result, seconds_remaining=0)


assert issubclass(FakeOtpAdapter, OtpDeliveryPort.__class__) or isinstance(
    FakeOtpAdapter(), OtpDeliveryPort
)
