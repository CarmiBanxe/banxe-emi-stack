"""
tests/test_twilio_otp_adapter.py — Unit tests for TwilioOtpAdapter.

All HTTP calls are mocked — no real Twilio API calls.
Integration tests (real Twilio sandbox) are a separate CI job requiring
TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_VERIFY_SERVICE_SID secrets.

Tests: 11
Canon: ADR-029 + PORT-CONTRACTS-FREEZE-2026-05-08
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from services.auth.otp_delivery_port import OtpDeliveryPort, OtpDeliveryReceipt, OtpVerifyResult


@pytest.fixture()
def env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "ACtest000000000000000000000000000001")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "test_auth_token_000000000000000000")
    monkeypatch.setenv("TWILIO_VERIFY_SERVICE_SID", "VAtest00000000000000000000000000001")


@pytest.fixture()
def mock_http() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def adapter(env_vars: None, mock_http: MagicMock) -> object:
    with patch("services.auth.production.twilio_otp_adapter.httpx.Client", return_value=mock_http):
        from services.auth.production.twilio_otp_adapter import TwilioOtpAdapter

        return TwilioOtpAdapter(sandbox=True)


# ── Protocol conformance ──────────────────────────────────────────────────────


def test_twilio_adapter_satisfies_otp_delivery_port(env_vars: None, mock_http: MagicMock) -> None:
    with patch("services.auth.production.twilio_otp_adapter.httpx.Client", return_value=mock_http):
        from services.auth.production.twilio_otp_adapter import TwilioOtpAdapter

        assert isinstance(TwilioOtpAdapter(sandbox=True), OtpDeliveryPort)


def test_twilio_adapter_inherits_generate_otp(adapter: object) -> None:
    code = adapter.generate_otp()  # type: ignore[attr-defined]
    assert len(code) == 6
    assert code.isdigit()


# ── send_otp ──────────────────────────────────────────────────────────────────


def test_twilio_send_otp_calls_verifications_endpoint(
    adapter: object, mock_http: MagicMock
) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {
        "sid": "VE0001",
        "to": "+447700900001",
        "channel": "sms",
        "status": "pending",
    }
    mock_http.post.return_value = mock_resp

    receipt = adapter.send_otp(  # type: ignore[attr-defined]
        channel="sms", target="+447700900001", code="123456", ttl_seconds=300
    )

    call_args = mock_http.post.call_args
    assert "Verifications" in call_args[0][0]
    assert call_args[1]["data"]["CustomCode"] == "123456"
    assert call_args[1]["data"]["Channel"] == "sms"
    assert call_args[1]["data"]["To"] == "+447700900001"


def test_twilio_send_otp_returns_receipt(adapter: object, mock_http: MagicMock) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {
        "sid": "VE0001",
        "to": "+447700900001",
        "channel": "sms",
        "status": "pending",
    }
    mock_http.post.return_value = mock_resp

    receipt = adapter.send_otp(  # type: ignore[attr-defined]
        channel="sms", target="+447700900001", code="123456", ttl_seconds=300
    )

    assert isinstance(receipt, OtpDeliveryReceipt)
    assert receipt.delivery_id == "VE0001"
    assert receipt.channel == "sms"
    assert receipt.target == "+447700900001"


def test_twilio_send_otp_http_error_propagates(adapter: object, mock_http: MagicMock) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "rate limit", request=MagicMock(), response=mock_resp
    )
    mock_http.post.return_value = mock_resp

    with pytest.raises(httpx.HTTPStatusError):
        adapter.send_otp(channel="sms", target="+447700900001", code="111111", ttl_seconds=300)  # type: ignore[attr-defined]


# ── verify_otp ────────────────────────────────────────────────────────────────


def test_twilio_verify_otp_approved(adapter: object, mock_http: MagicMock) -> None:
    # first call = send, second call = verify
    send_resp = MagicMock()
    send_resp.status_code = 201
    send_resp.json.return_value = {"sid": "VE0001", "status": "pending"}

    verify_resp = MagicMock()
    verify_resp.status_code = 200
    verify_resp.json.return_value = {"sid": "VE0001", "status": "approved"}
    mock_http.post.side_effect = [send_resp, verify_resp]

    adapter.send_otp(channel="sms", target="+447700900001", code="123456", ttl_seconds=300)  # type: ignore[attr-defined]
    result = adapter.verify_otp(channel="sms", target="+447700900001", code="123456")  # type: ignore[attr-defined]

    assert isinstance(result, OtpVerifyResult)
    assert result.success is True
    assert result.message == "approved"
    assert result.delivery_id == "VE0001"


def test_twilio_verify_otp_pending_returns_failure(adapter: object, mock_http: MagicMock) -> None:
    verify_resp = MagicMock()
    verify_resp.status_code = 200
    verify_resp.json.return_value = {"sid": "VE0001", "status": "pending"}
    mock_http.post.return_value = verify_resp

    result = adapter.verify_otp(channel="sms", target="+447700900001", code="wrong")  # type: ignore[attr-defined]
    assert result.success is False
    assert result.message == "pending"


def test_twilio_verify_otp_404_returns_failure(adapter: object, mock_http: MagicMock) -> None:
    verify_resp = MagicMock()
    verify_resp.status_code = 404
    verify_resp.raise_for_status.return_value = None
    mock_http.post.return_value = verify_resp

    result = adapter.verify_otp(channel="sms", target="+447700900001", code="000000")  # type: ignore[attr-defined]
    assert result.success is False
    assert "expired" in result.message.lower() or "not found" in result.message.lower()


# ── can_resend (inherited) ────────────────────────────────────────────────────


def test_twilio_can_resend_before_any_send(adapter: object) -> None:
    check = adapter.can_resend(channel="sms", target="+447700900001", min_interval_seconds=60)  # type: ignore[attr-defined]
    assert check.can_resend is True
    assert check.seconds_remaining == 0


def test_twilio_close_calls_http_close(adapter: object, mock_http: MagicMock) -> None:
    adapter.close()  # type: ignore[attr-defined]
    mock_http.close.assert_called_once()
