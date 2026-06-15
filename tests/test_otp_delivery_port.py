"""
tests/test_otp_delivery_port.py — Contract tests for OtpDeliveryPort.

Coverage: port Protocol structural checks + frozen Pydantic model invariants.
Tests: 12  |  No external deps (all in-process).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import inspect

from pydantic import ValidationError
import pytest

from services.auth.legacy.legacy_otp_adapter import LegacyOtpAdapter
from services.auth.otp_delivery_port import (
    OtpDeliveryPort,
    OtpDeliveryReceipt,
    OtpVerifyResult,
    ResendCheck,
)

# ── Protocol structural tests ─────────────────────────────────────────────────


def test_otp_delivery_port_is_runtime_checkable() -> None:
    """@runtime_checkable must allow isinstance() checks against the Protocol."""
    adapter = LegacyOtpAdapter()
    assert isinstance(adapter, OtpDeliveryPort)


def test_port_has_generate_otp_method() -> None:
    assert hasattr(OtpDeliveryPort, "generate_otp")


def test_port_has_send_otp_method() -> None:
    assert hasattr(OtpDeliveryPort, "send_otp")


def test_port_has_verify_otp_method() -> None:
    assert hasattr(OtpDeliveryPort, "verify_otp")


def test_port_has_can_resend_method() -> None:
    assert hasattr(OtpDeliveryPort, "can_resend")


def test_generate_otp_signature_keyword_only() -> None:
    """generate_otp params length and alphabet must be keyword-only."""
    sig = inspect.signature(OtpDeliveryPort.generate_otp)
    params = dict(sig.parameters)
    assert "length" in params
    assert "alphabet" in params
    assert params["length"].kind == inspect.Parameter.KEYWORD_ONLY
    assert params["alphabet"].kind == inspect.Parameter.KEYWORD_ONLY


def test_send_otp_signature_has_all_params() -> None:
    sig = inspect.signature(OtpDeliveryPort.send_otp)
    params = set(sig.parameters)
    assert {"channel", "target", "code", "ttl_seconds"}.issubset(params)


def test_verify_otp_signature_has_all_params() -> None:
    sig = inspect.signature(OtpDeliveryPort.verify_otp)
    params = set(sig.parameters)
    assert {"channel", "target", "code"}.issubset(params)


def test_can_resend_signature_has_all_params() -> None:
    sig = inspect.signature(OtpDeliveryPort.can_resend)
    params = set(sig.parameters)
    assert {"channel", "target", "min_interval_seconds"}.issubset(params)


# ── Frozen model tests ────────────────────────────────────────────────────────

_NOW = datetime.now(UTC)
_LATER = _NOW + timedelta(minutes=5)


def test_otp_delivery_receipt_is_frozen() -> None:
    receipt = OtpDeliveryReceipt(
        delivery_id="d1",
        channel="sms",
        target="+1234",
        sent_at=_NOW,
        expires_at=_LATER,
    )
    with pytest.raises((TypeError, AttributeError, ValidationError)):
        receipt.delivery_id = "mutated"  # type: ignore[misc]


def test_otp_verify_result_is_frozen() -> None:
    result = OtpVerifyResult(success=True, message="ok")
    with pytest.raises((TypeError, AttributeError, ValidationError)):
        result.success = False  # type: ignore[misc]


def test_resend_check_is_frozen() -> None:
    check = ResendCheck(can_resend=True, seconds_remaining=0)
    with pytest.raises((TypeError, AttributeError, ValidationError)):
        check.can_resend = False  # type: ignore[misc]


def test_otp_verify_result_delivery_id_is_optional() -> None:
    result_no_id = OtpVerifyResult(success=False, message="err")
    assert result_no_id.delivery_id is None

    result_with_id = OtpVerifyResult(success=True, message="ok", delivery_id="abc")
    assert result_with_id.delivery_id == "abc"
