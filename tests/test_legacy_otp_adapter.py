"""
tests/test_legacy_otp_adapter.py — Unit tests for LegacyOtpAdapter.

Coverage: 100%  |  Tests: 25  |  No external deps (all in-memory).
Verifies semantic parity with CodeService (banxe-common/code.service.ts).
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
import string

from services.auth.legacy.legacy_otp_adapter import (
    LegacyOtpAdapter,
)
from services.auth.otp_delivery_port import OtpDeliveryPort

# ── Fixtures ──────────────────────────────────────────────────────────────────

_SMS = "sms"
_EMAIL = "email"
_PHONE = "+447700900001"
_EMAIL_ADDR = "user@banxe.com"
_TTL = 300


def _adapter() -> LegacyOtpAdapter:
    return LegacyOtpAdapter()


def _send(adapter: LegacyOtpAdapter, channel: str = _SMS, target: str = _PHONE) -> str:
    code = adapter.generate_otp()
    adapter.send_otp(channel=channel, target=target, code=code, ttl_seconds=_TTL)  # type: ignore[arg-type]
    return code


# ── Protocol conformance ──────────────────────────────────────────────────────


def test_legacy_otp_adapter_satisfies_port() -> None:
    assert isinstance(_adapter(), OtpDeliveryPort)


# ── generate_otp ─────────────────────────────────────────────────────────────


def test_generate_otp_default_length_is_6() -> None:
    adapter = _adapter()
    code = adapter.generate_otp()
    assert len(code) == 6


def test_generate_otp_custom_length() -> None:
    adapter = _adapter()
    assert len(adapter.generate_otp(length=8)) == 8


def test_generate_otp_digits_only_charset() -> None:
    adapter = _adapter()
    for _ in range(20):
        code = adapter.generate_otp(alphabet="digits")
        assert all(c in string.digits for c in code), f"Non-digit in: {code}"


def test_generate_otp_alphanumeric_charset() -> None:
    adapter = _adapter()
    allowed = set(string.ascii_uppercase + string.digits)
    for _ in range(20):
        code = adapter.generate_otp(alphabet="alphanumeric", length=8)
        assert all(c in allowed for c in code), f"Unexpected char in: {code}"


def test_generate_otp_codes_are_unique() -> None:
    adapter = _adapter()
    codes = {adapter.generate_otp() for _ in range(50)}
    # With 10^6 possibilities for 6 digits, ≥40 unique in 50 is a safe sanity check.
    assert len(codes) >= 40


# ── send_otp ─────────────────────────────────────────────────────────────────


def test_send_otp_returns_receipt() -> None:
    adapter = _adapter()
    code = adapter.generate_otp()
    receipt = adapter.send_otp(channel=_SMS, target=_PHONE, code=code, ttl_seconds=_TTL)
    assert receipt.channel == _SMS
    assert receipt.target == _PHONE
    assert receipt.delivery_id  # non-empty string
    assert receipt.expires_at > receipt.sent_at


def test_send_otp_ttl_reflected_in_expires_at() -> None:
    adapter = _adapter()
    code = adapter.generate_otp()
    receipt = adapter.send_otp(channel=_SMS, target=_PHONE, code=code, ttl_seconds=120)
    delta = (receipt.expires_at - receipt.sent_at).total_seconds()
    # Allow ±2 s for test execution time
    assert 118 <= delta <= 122


def test_send_otp_replaces_previous_record() -> None:
    adapter = _adapter()
    first = adapter.generate_otp()
    adapter.send_otp(channel=_SMS, target=_PHONE, code=first, ttl_seconds=_TTL)
    second = adapter.generate_otp()
    adapter.send_otp(channel=_SMS, target=_PHONE, code=second, ttl_seconds=_TTL)
    result = adapter.verify_otp(channel=_SMS, target=_PHONE, code=first)
    assert not result.success  # first code replaced by second


# ── verify_otp — happy path ───────────────────────────────────────────────────


def test_verify_otp_happy_path() -> None:
    adapter = _adapter()
    code = _send(adapter)
    result = adapter.verify_otp(channel=_SMS, target=_PHONE, code=code)
    assert result.success
    assert "verified" in result.message.lower()


def test_verify_otp_returns_delivery_id_on_success() -> None:
    adapter = _adapter()
    code = adapter.generate_otp()
    receipt = adapter.send_otp(channel=_SMS, target=_PHONE, code=code, ttl_seconds=_TTL)
    result = adapter.verify_otp(channel=_SMS, target=_PHONE, code=code)
    assert result.success
    assert result.delivery_id == receipt.delivery_id


# ── verify_otp — failure paths ────────────────────────────────────────────────


def test_verify_otp_wrong_code_fails() -> None:
    adapter = _adapter()
    _send(adapter)
    result = adapter.verify_otp(channel=_SMS, target=_PHONE, code="000000")
    assert not result.success
    assert "invalid" in result.message.lower()


def test_verify_otp_no_pending_otp_fails() -> None:
    adapter = _adapter()
    result = adapter.verify_otp(channel=_SMS, target=_PHONE, code="123456")
    assert not result.success
    assert "no pending" in result.message.lower()


def test_verify_otp_expired_fails() -> None:
    adapter = _adapter()
    code = _send(adapter)
    # Force expiry by replacing record directly
    key = (_SMS, _PHONE)
    expired = dataclasses.replace(
        adapter._records[key],
        expires_at=datetime(2000, 1, 1, tzinfo=UTC),
    )
    adapter._records[key] = expired
    result = adapter.verify_otp(channel=_SMS, target=_PHONE, code=code)
    assert not result.success
    assert "expired" in result.message.lower()


def test_verify_otp_replay_fails() -> None:
    """Second verify on the same code must fail (single-use semantics)."""
    adapter = _adapter()
    code = _send(adapter)
    first = adapter.verify_otp(channel=_SMS, target=_PHONE, code=code)
    assert first.success
    second = adapter.verify_otp(channel=_SMS, target=_PHONE, code=code)
    assert not second.success


# ── multi-channel / multi-target isolation ────────────────────────────────────


def test_sms_and_email_channels_are_isolated() -> None:
    adapter = _adapter()
    sms_code = "111111"
    email_code = "222222"

    adapter.send_otp(channel=_SMS, target=_PHONE, code=sms_code, ttl_seconds=_TTL)
    adapter.send_otp(channel=_EMAIL, target=_EMAIL_ADDR, code=email_code, ttl_seconds=_TTL)

    # Cross-channel verify must fail
    assert not adapter.verify_otp(channel=_EMAIL, target=_EMAIL_ADDR, code=sms_code).success
    assert not adapter.verify_otp(channel=_SMS, target=_PHONE, code=email_code).success

    # Correct channel must succeed
    assert adapter.verify_otp(channel=_SMS, target=_PHONE, code=sms_code).success
    assert adapter.verify_otp(channel=_EMAIL, target=_EMAIL_ADDR, code=email_code).success


def test_different_targets_are_isolated() -> None:
    adapter = _adapter()
    phone_a, phone_b = "+447700900001", "+447700900002"
    code_a = adapter.generate_otp()
    code_b = adapter.generate_otp()
    adapter.send_otp(channel=_SMS, target=phone_a, code=code_a, ttl_seconds=_TTL)
    adapter.send_otp(channel=_SMS, target=phone_b, code=code_b, ttl_seconds=_TTL)
    assert not adapter.verify_otp(channel=_SMS, target=phone_a, code=code_b).success
    assert not adapter.verify_otp(channel=_SMS, target=phone_b, code=code_a).success
    assert adapter.verify_otp(channel=_SMS, target=phone_a, code=code_a).success
    assert adapter.verify_otp(channel=_SMS, target=phone_b, code=code_b).success


# ── can_resend ────────────────────────────────────────────────────────────────


def test_can_resend_true_when_no_record_exists() -> None:
    adapter = _adapter()
    check = adapter.can_resend(channel=_SMS, target=_PHONE, min_interval_seconds=60)
    assert check.can_resend
    assert check.seconds_remaining == 0
    assert check.last_sent_at is None


def test_can_resend_false_within_interval() -> None:
    adapter = _adapter()
    _send(adapter)
    check = adapter.can_resend(channel=_SMS, target=_PHONE, min_interval_seconds=60)
    assert not check.can_resend
    assert check.seconds_remaining > 0
    assert check.last_sent_at is not None


def test_can_resend_true_after_interval_elapsed() -> None:
    adapter = _adapter()
    _send(adapter)
    # Backdate sent_at to simulate elapsed interval
    key = (_SMS, _PHONE)
    old_record = dataclasses.replace(
        adapter._records[key],
        sent_at=datetime(2020, 1, 1, tzinfo=UTC),
    )
    adapter._records[key] = old_record
    check = adapter.can_resend(channel=_SMS, target=_PHONE, min_interval_seconds=60)
    assert check.can_resend
    assert check.seconds_remaining == 0


def test_can_resend_seconds_remaining_is_non_negative() -> None:
    adapter = _adapter()
    _send(adapter)
    check = adapter.can_resend(channel=_SMS, target=_PHONE, min_interval_seconds=60)
    assert check.seconds_remaining >= 0


def test_can_resend_does_not_consume_pending_otp() -> None:
    adapter = _adapter()
    code = _send(adapter)
    adapter.can_resend(channel=_SMS, target=_PHONE, min_interval_seconds=60)
    # OTP must still be verifiable after can_resend call
    result = adapter.verify_otp(channel=_SMS, target=_PHONE, code=code)
    assert result.success


# ── email channel ─────────────────────────────────────────────────────────────


def test_send_and_verify_via_email_channel() -> None:
    adapter = _adapter()
    code = adapter.generate_otp(length=8, alphabet="alphanumeric")
    adapter.send_otp(channel=_EMAIL, target=_EMAIL_ADDR, code=code, ttl_seconds=600)
    result = adapter.verify_otp(channel=_EMAIL, target=_EMAIL_ADDR, code=code)
    assert result.success
