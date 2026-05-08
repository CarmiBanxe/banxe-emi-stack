"""
tests/test_sendgrid_otp_adapter.py — Unit tests for SendGridOtpAdapter.

All HTTP calls are mocked — no real SendGrid API calls.
Integration tests (real SendGrid sandbox) are a separate CI job requiring
SENDGRID_API_KEY / SENDGRID_FROM_EMAIL secrets.

Tests: 10
Canon: ADR-029 + PORT-CONTRACTS-FREEZE-2026-05-08
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from services.auth.otp_delivery_port import OtpDeliveryPort, OtpDeliveryReceipt, OtpVerifyResult


@pytest.fixture()
def env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENDGRID_API_KEY", "SG.test_key_000000000000000000000000000")
    monkeypatch.setenv("SENDGRID_FROM_EMAIL", "otp-noreply@banxe.com")


@pytest.fixture()
def mock_http() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def adapter(env_vars: None, mock_http: MagicMock) -> object:
    with patch(
        "services.auth.production.sendgrid_otp_adapter.httpx.Client", return_value=mock_http
    ):
        from services.auth.production.sendgrid_otp_adapter import SendGridOtpAdapter

        return SendGridOtpAdapter(sandbox=True)


# ── Protocol conformance ──────────────────────────────────────────────────────


def test_sendgrid_adapter_satisfies_otp_delivery_port(env_vars: None, mock_http: MagicMock) -> None:
    with patch(
        "services.auth.production.sendgrid_otp_adapter.httpx.Client", return_value=mock_http
    ):
        from services.auth.production.sendgrid_otp_adapter import SendGridOtpAdapter

        assert isinstance(SendGridOtpAdapter(sandbox=True), OtpDeliveryPort)


def test_sendgrid_adapter_inherits_generate_otp(adapter: object) -> None:
    code = adapter.generate_otp()  # type: ignore[attr-defined]
    assert len(code) == 6
    assert code.isdigit()


# ── send_otp ──────────────────────────────────────────────────────────────────


def test_sendgrid_send_otp_calls_mail_send_endpoint(adapter: object, mock_http: MagicMock) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 202
    mock_http.post.return_value = mock_resp

    adapter.send_otp(channel="email", target="user@banxe.com", code="654321", ttl_seconds=600)  # type: ignore[attr-defined]

    call_args = mock_http.post.call_args
    assert "/v3/mail/send" in call_args[0][0]


def test_sendgrid_send_otp_sandbox_mode_enabled(adapter: object, mock_http: MagicMock) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 202
    mock_http.post.return_value = mock_resp

    adapter.send_otp(channel="email", target="user@banxe.com", code="654321", ttl_seconds=600)  # type: ignore[attr-defined]

    payload = mock_http.post.call_args[1]["json"]
    assert payload["mail_settings"]["sandbox_mode"]["enable"] is True


def test_sendgrid_send_otp_returns_receipt(adapter: object, mock_http: MagicMock) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 202
    mock_http.post.return_value = mock_resp

    receipt = adapter.send_otp(  # type: ignore[attr-defined]
        channel="email", target="user@banxe.com", code="654321", ttl_seconds=600
    )

    assert isinstance(receipt, OtpDeliveryReceipt)
    assert receipt.channel == "email"
    assert receipt.target == "user@banxe.com"


def test_sendgrid_send_otp_sms_raises_value_error(adapter: object, mock_http: MagicMock) -> None:
    with pytest.raises(ValueError, match="channel='email'"):
        adapter.send_otp(channel="sms", target="+447700900001", code="111111", ttl_seconds=300)  # type: ignore[attr-defined]


def test_sendgrid_send_otp_http_error_propagates(adapter: object, mock_http: MagicMock) -> None:
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "unauthorized", request=MagicMock(), response=mock_resp
    )
    mock_http.post.return_value = mock_resp

    with pytest.raises(httpx.HTTPStatusError):
        adapter.send_otp(channel="email", target="user@banxe.com", code="000000", ttl_seconds=300)  # type: ignore[attr-defined]


# ── verify_otp (in-memory, inherited) ────────────────────────────────────────


def test_sendgrid_verify_otp_round_trip(adapter: object, mock_http: MagicMock) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 202
    mock_http.post.return_value = mock_resp

    adapter.send_otp(channel="email", target="user@banxe.com", code="999888", ttl_seconds=600)  # type: ignore[attr-defined]
    result = adapter.verify_otp(channel="email", target="user@banxe.com", code="999888")  # type: ignore[attr-defined]

    assert isinstance(result, OtpVerifyResult)
    assert result.success is True


def test_sendgrid_verify_otp_wrong_code_fails(adapter: object, mock_http: MagicMock) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 202
    mock_http.post.return_value = mock_resp

    adapter.send_otp(channel="email", target="user@banxe.com", code="999888", ttl_seconds=600)  # type: ignore[attr-defined]
    result = adapter.verify_otp(channel="email", target="user@banxe.com", code="000000")  # type: ignore[attr-defined]

    assert result.success is False


# ── can_resend (inherited) ────────────────────────────────────────────────────


def test_sendgrid_can_resend_before_any_send(adapter: object) -> None:
    check = adapter.can_resend(channel="email", target="user@banxe.com", min_interval_seconds=60)  # type: ignore[attr-defined]
    assert check.can_resend is True
