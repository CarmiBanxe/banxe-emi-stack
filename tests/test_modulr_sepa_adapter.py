"""
tests/test_modulr_sepa_adapter.py — Unit tests for ModulrSepaAdapter.

All HTTP calls are mocked — no real Modulr API calls.
Integration tests (real Modulr sandbox) are a separate CI job requiring
MODULR_API_KEY / MODULR_API_SECRET secrets.

Tests: 18
Canon: ADR-025 §15-16 + PORT-CONTRACTS-FREEZE-2026-05-08 + [IL-SEPA-PROD-01]
"""

from __future__ import annotations

from datetime import UTC
from decimal import Decimal
from unittest.mock import MagicMock

import httpx
import pytest

from services.payment.payment_port import (
    BankAccount,
    PaymentDirection,
    PaymentIntent,
    PaymentRail,
    PaymentResult,
    PaymentStatus,
)

# ── Shared test data ──────────────────────────────────────────────────────────

_VALID_IBAN = "GB29NWBK60161331926819"
_VALID_BIC = "NWBKGB2L"

_PAYMENT_SUBMITTED = {
    "id": "pay-001",
    "status": "SUBMITTED",
    "amount": 50000,
    "currency": "EUR",
    "type": "SEPA_CT",
    "externalReference": "idem-key-001",
}

_PAYMENT_PROCESSED = {**_PAYMENT_SUBMITTED, "status": "PROCESSED"}
_PAYMENT_FAILED = {**_PAYMENT_SUBMITTED, "status": "FAILED"}
_PAYMENT_INSTANT = {**_PAYMENT_SUBMITTED, "type": "SEPA_INSTANT", "status": "PROCESSING"}


def _make_resp(json_data: object, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    return resp


@pytest.fixture()
def env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODULR_API_KEY", "test_api_key_000000000000")
    monkeypatch.setenv("MODULR_API_SECRET", "test_api_secret_00000000")
    monkeypatch.setenv("MODULR_EUR_ACCOUNT_ID", "A1EUR000001")


@pytest.fixture()
def mock_http() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def adapter(env_vars: None, mock_http: MagicMock) -> object:
    from unittest.mock import patch

    with patch(
        "services.payment.production.modulr_sepa_adapter.httpx.Client",
        return_value=mock_http,
    ):
        from services.payment.production.modulr_sepa_adapter import ModulrSepaAdapter

        return ModulrSepaAdapter(sandbox=True)


def _make_intent(
    rail: PaymentRail = PaymentRail.SEPA_CT,
    amount: str = "500.00",
    iban: str = _VALID_IBAN,
    bic: str = _VALID_BIC,
) -> PaymentIntent:
    from datetime import datetime

    return PaymentIntent(
        idempotency_key="idem-key-001",
        rail=rail,
        direction=PaymentDirection.OUTBOUND,
        amount=Decimal(amount),
        currency="EUR",
        debtor_account=BankAccount(account_holder_name="Banxe EUR", iban="DE89370400440532013000"),
        creditor_account=BankAccount(account_holder_name="Alice Smith", iban=iban, bic=bic),
        reference="Invoice 12345",
        end_to_end_id="E2E-2026-0001",
        requested_at=datetime.now(UTC),
    )


# ── Protocol structure ────────────────────────────────────────────────────────


def test_adapter_has_all_port_methods(adapter: object) -> None:
    for method in ("submit_payment", "get_payment_status", "health"):
        assert callable(getattr(adapter, method, None)), f"Missing port method: {method}"


# ── submit_payment ────────────────────────────────────────────────────────────


def test_submit_payment_sends_post_to_accounts_endpoint(
    adapter: object, mock_http: MagicMock
) -> None:
    mock_http.request.return_value = _make_resp(_PAYMENT_SUBMITTED)

    adapter.submit_payment(_make_intent())  # type: ignore[attr-defined]

    call = mock_http.request.call_args
    assert call[0][0] == "POST"
    assert "/accounts/" in call[0][1]
    assert "/payments" in call[0][1]


def test_submit_payment_returns_payment_result(adapter: object, mock_http: MagicMock) -> None:
    mock_http.request.return_value = _make_resp(_PAYMENT_SUBMITTED)

    result = adapter.submit_payment(_make_intent())  # type: ignore[attr-defined]

    assert isinstance(result, PaymentResult)
    assert result.provider_payment_id == "pay-001"
    assert result.status == PaymentStatus.PENDING
    assert result.idempotency_key == "idem-key-001"


def test_submit_payment_maps_processed_to_completed(adapter: object, mock_http: MagicMock) -> None:
    mock_http.request.return_value = _make_resp(_PAYMENT_PROCESSED)

    result = adapter.submit_payment(_make_intent())  # type: ignore[attr-defined]

    assert result.status == PaymentStatus.COMPLETED


def test_submit_payment_sepa_instant_maps_processing(adapter: object, mock_http: MagicMock) -> None:
    mock_http.request.return_value = _make_resp(_PAYMENT_INSTANT)

    result = adapter.submit_payment(  # type: ignore[attr-defined]
        _make_intent(rail=PaymentRail.SEPA_INSTANT)
    )

    assert result.status == PaymentStatus.PROCESSING


def test_submit_payment_sets_x_mod_nonce_header(adapter: object, mock_http: MagicMock) -> None:
    mock_http.request.return_value = _make_resp(_PAYMENT_SUBMITTED)

    adapter.submit_payment(_make_intent())  # type: ignore[attr-defined]

    headers = mock_http.request.call_args[1]["headers"]
    assert "x-mod-nonce" in headers
    assert headers["x-mod-nonce"] == "idem-key-001"


def test_submit_payment_sets_basic_auth_header(adapter: object, mock_http: MagicMock) -> None:
    mock_http.request.return_value = _make_resp(_PAYMENT_SUBMITTED)

    adapter.submit_payment(_make_intent())  # type: ignore[attr-defined]

    headers = mock_http.request.call_args[1]["headers"]
    assert "Authorization" in headers
    assert headers["Authorization"].startswith("Basic ")


def test_submit_payment_rejects_fps_rail(adapter: object) -> None:
    from datetime import datetime

    intent = PaymentIntent(
        idempotency_key="idem-fps-001",
        rail=PaymentRail.FPS,
        direction=PaymentDirection.OUTBOUND,
        amount=Decimal("100.00"),
        currency="GBP",
        debtor_account=BankAccount(
            account_holder_name="Banxe GBP",
            sort_code="20-20-15",
            account_number="12345678",
        ),
        creditor_account=BankAccount(
            account_holder_name="Bob Jones",
            sort_code="40-47-84",
            account_number="87654321",
        ),
        reference="FPS payment",
        end_to_end_id="E2E-FPS-001",
        requested_at=datetime.now(UTC),
    )

    result = adapter.submit_payment(intent)  # type: ignore[attr-defined]

    assert result.status == PaymentStatus.FAILED
    assert result.error_code == "unsupported_rail"


def test_submit_payment_rejects_invalid_iban(adapter: object) -> None:
    result = adapter.submit_payment(  # type: ignore[attr-defined]
        _make_intent(iban="INVALID-IBAN-0000")
    )

    assert result.status == PaymentStatus.FAILED
    assert result.error_code == "invalid_iban"


def test_submit_payment_rejects_invalid_bic(adapter: object) -> None:
    result = adapter.submit_payment(  # type: ignore[attr-defined]
        _make_intent(bic="BAD!")
    )

    assert result.status == PaymentStatus.FAILED
    assert result.error_code == "invalid_bic"


def test_submit_payment_blocks_sct_inst_above_100k(adapter: object) -> None:
    result = adapter.submit_payment(  # type: ignore[attr-defined]
        _make_intent(rail=PaymentRail.SEPA_INSTANT, amount="100000.01")
    )

    assert result.status == PaymentStatus.FAILED
    assert result.error_code == "amount_exceeds_sct_inst_max"


def test_submit_payment_allows_sct_inst_at_100k(adapter: object, mock_http: MagicMock) -> None:
    mock_http.request.return_value = _make_resp(_PAYMENT_INSTANT)

    result = adapter.submit_payment(  # type: ignore[attr-defined]
        _make_intent(rail=PaymentRail.SEPA_INSTANT, amount="100000.00")
    )

    assert (
        result.status != PaymentStatus.FAILED or result.error_code != "amount_exceeds_sct_inst_max"
    )


def test_submit_payment_failsafe_on_http_error(adapter: object, mock_http: MagicMock) -> None:
    err_resp = _make_resp({}, status_code=500)
    err_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "server error", request=MagicMock(), response=err_resp
    )
    mock_http.request.return_value = err_resp

    result = adapter.submit_payment(_make_intent())  # type: ignore[attr-defined]

    assert result.status == PaymentStatus.FAILED
    assert result.error_code == "http_500"


# ── get_payment_status ────────────────────────────────────────────────────────


def test_get_payment_status_calls_payments_get(adapter: object, mock_http: MagicMock) -> None:
    mock_http.request.return_value = _make_resp(_PAYMENT_PROCESSED)

    adapter.get_payment_status("pay-001")  # type: ignore[attr-defined]

    call = mock_http.request.call_args
    assert call[0][0] == "GET"
    assert "pay-001" in call[0][1]


def test_get_payment_status_returns_completed(adapter: object, mock_http: MagicMock) -> None:
    mock_http.request.return_value = _make_resp(_PAYMENT_PROCESSED)

    result = adapter.get_payment_status("pay-001")  # type: ignore[attr-defined]

    assert isinstance(result, PaymentResult)
    assert result.status == PaymentStatus.COMPLETED
    assert result.amount == Decimal("500.00")


def test_get_payment_status_failsafe_on_404(adapter: object, mock_http: MagicMock) -> None:
    err_resp = _make_resp({}, status_code=404)
    err_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "not found", request=MagicMock(), response=err_resp
    )
    mock_http.request.return_value = err_resp

    result = adapter.get_payment_status("nonexistent")  # type: ignore[attr-defined]

    assert result.status == PaymentStatus.FAILED
    assert result.error_code == "http_404"


# ── health ────────────────────────────────────────────────────────────────────


def test_health_returns_true_on_200(adapter: object, mock_http: MagicMock) -> None:
    mock_http.request.return_value = _make_resp({"status": "OK"})
    assert adapter.health() is True  # type: ignore[attr-defined]


def test_health_returns_false_on_exception(adapter: object, mock_http: MagicMock) -> None:
    mock_http.request.side_effect = httpx.ConnectError("unreachable")
    assert adapter.health() is False  # type: ignore[attr-defined]


# ── close ─────────────────────────────────────────────────────────────────────


def test_close_calls_http_close(adapter: object, mock_http: MagicMock) -> None:
    adapter.close()  # type: ignore[attr-defined]
    mock_http.close.assert_called_once()
