"""
tests/test_midaz_crypto_adapter.py — Unit tests for MidazCryptoAdapter.

All HTTP calls are mocked — no real Midaz API calls.
Integration tests (real Midaz sandbox) are a separate CI job requiring MIDAZ_API_KEY secret.

Tests: 24
Canon: ADR-031 (proposed) + PORT-CONTRACTS-FREEZE-2026-05-08 + [IL-CRYPTO-PROD-01]
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import httpx
import pytest

from services.ledger.crypto_ledger_port import (
    CryptoLedgerPort,
    CryptoTransactionRequest,
    CryptoTransactionStatus,
    FeePriority,
    SupportedBlockchain,
)

# ── Shared test data ──────────────────────────────────────────────────────────

_BALANCE_RESPONSE = {
    "items": [
        {"assetCode": "BTC", "available": 500000000, "onHold": 10000000},
    ]
}

_WALLET_RESPONSE = {
    "id": "wallet-abc-001",
    "address": "bc1qxyz000",
    "blockchainAddress": "bc1qxyz000",
    "createdAt": "2026-05-09T10:00:00Z",
}

_TX_PENDING = {
    "externalId": "tx-idem-001",
    "txHash": None,
    "status": "PENDING",
    "amount": 1000000000,
    "fee": 5000,
    "currency": "BTC",
    "fromWalletId": "wallet-abc-001",
    "toAddress": "bc1qdest000",
    "createdAt": "2026-05-09T10:00:00Z",
    "confirmedAt": None,
}

_TX_CONFIRMED = {**_TX_PENDING, "status": "CONFIRMED", "txHash": "deadbeef1234"}
_TX_FAILED = {**_TX_PENDING, "status": "FAILED"}
_TX_APPROVED = {**_TX_PENDING, "status": "APPROVED", "txHash": "cafebabe5678"}


def _make_resp(json_data: object, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    return resp


@pytest.fixture()
def env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIDAZ_API_KEY", "test_midaz_api_key_000000000000")


@pytest.fixture()
def mock_http() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def adapter(env_vars: None, mock_http: MagicMock) -> object:
    with patch(
        "services.ledger.production.midaz_crypto_adapter.httpx.Client",
        return_value=mock_http,
    ):
        from services.ledger.production.midaz_crypto_adapter import MidazCryptoAdapter

        return MidazCryptoAdapter(sandbox=True)


def _make_tx_request(
    blockchain: SupportedBlockchain = SupportedBlockchain.BTC,
    amount: str = "10.00",
) -> CryptoTransactionRequest:
    return CryptoTransactionRequest(
        tx_id="tx-idem-001",
        from_wallet_id="wallet-abc-001",
        to_address="bc1qdest000",
        blockchain=blockchain,
        amount=Decimal(amount),
        currency="BTC",
        fee_level=FeePriority.MEDIUM,
        customer_id="cust-001",
    )


# ── Protocol structure ────────────────────────────────────────────────────────


def test_adapter_satisfies_crypto_ledger_port(adapter: object) -> None:
    assert isinstance(adapter, CryptoLedgerPort)


def test_adapter_has_all_port_methods(adapter: object) -> None:
    for method in (
        "get_balance",
        "create_wallet_address",
        "create_tx",
        "get_fee_estimate",
        "health",
    ):
        assert callable(getattr(adapter, method, None)), f"Missing port method: {method}"


# ── get_balance ───────────────────────────────────────────────────────────────


def test_get_balance_calls_wallets_balances_endpoint(adapter: object, mock_http: MagicMock) -> None:
    mock_http.request.return_value = _make_resp(_BALANCE_RESPONSE)

    adapter.get_balance("wallet-abc-001", SupportedBlockchain.BTC)  # type: ignore[attr-defined]

    call = mock_http.request.call_args
    assert call[0][0] == "GET"
    assert "wallet-abc-001" in call[0][1]
    assert "balances" in call[0][1]


def test_get_balance_returns_crypto_balance(adapter: object, mock_http: MagicMock) -> None:
    mock_http.request.return_value = _make_resp(_BALANCE_RESPONSE)

    result = adapter.get_balance("wallet-abc-001", SupportedBlockchain.BTC)  # type: ignore[attr-defined]

    assert type(result).__name__ == "CryptoBalance"
    assert result.wallet_id == "wallet-abc-001"
    assert result.blockchain == SupportedBlockchain.BTC
    assert result.confirmed_balance == Decimal("5.00")  # 500_000_000 / 10^8
    assert result.unconfirmed_balance == Decimal("0.1")  # 10_000_000 / 10^8
    assert result.currency == "BTC"


def test_get_balance_preserves_decimal_precision(adapter: object, mock_http: MagicMock) -> None:
    resp = {"items": [{"assetCode": "BTC", "available": 12345678, "onHold": 0}]}
    mock_http.request.return_value = _make_resp(resp)

    result = adapter.get_balance("w-001", SupportedBlockchain.BTC)  # type: ignore[attr-defined]

    assert isinstance(result.confirmed_balance, Decimal)
    assert result.confirmed_balance == Decimal("0.12345678")


def test_get_balance_raises_on_http_error(adapter: object, mock_http: MagicMock) -> None:
    err_resp = _make_resp({}, status_code=503)
    err_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "service unavailable", request=MagicMock(), response=err_resp
    )
    mock_http.request.return_value = err_resp

    with pytest.raises(Exception) as exc_info:
        adapter.get_balance("wallet-abc-001", SupportedBlockchain.BTC)  # type: ignore[attr-defined]

    assert type(exc_info.value).__name__ == "CryptoLedgerError"
    assert exc_info.value.code == "http_503"  # type: ignore[attr-defined]


def test_get_balance_sets_bearer_auth_header(adapter: object, mock_http: MagicMock) -> None:
    mock_http.request.return_value = _make_resp(_BALANCE_RESPONSE)

    adapter.get_balance("wallet-abc-001", SupportedBlockchain.BTC)  # type: ignore[attr-defined]

    headers = mock_http.request.call_args[1]["headers"]
    assert "Authorization" in headers
    assert headers["Authorization"].startswith("Bearer ")


# ── create_wallet_address ─────────────────────────────────────────────────────


def test_create_wallet_address_sends_post_to_wallets(adapter: object, mock_http: MagicMock) -> None:
    mock_http.request.return_value = _make_resp(_WALLET_RESPONSE)

    adapter.create_wallet_address("cust-001", SupportedBlockchain.BTC)  # type: ignore[attr-defined]

    call = mock_http.request.call_args
    assert call[0][0] == "POST"
    assert call[0][1].endswith("/v1/wallets")


def test_create_wallet_address_returns_crypto_wallet_address(
    adapter: object, mock_http: MagicMock
) -> None:
    mock_http.request.return_value = _make_resp(_WALLET_RESPONSE)

    result = adapter.create_wallet_address("cust-001", SupportedBlockchain.BTC)  # type: ignore[attr-defined]

    assert type(result).__name__ == "CryptoWalletAddress"
    assert result.wallet_id == "wallet-abc-001"
    assert result.customer_id == "cust-001"
    assert result.blockchain == SupportedBlockchain.BTC
    assert result.address == "bc1qxyz000"


def test_create_wallet_address_raises_on_409(adapter: object, mock_http: MagicMock) -> None:
    err_resp = _make_resp({"error": "conflict"}, status_code=409)
    err_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "conflict", request=MagicMock(), response=err_resp
    )
    mock_http.request.return_value = err_resp

    with pytest.raises(Exception) as exc_info:
        adapter.create_wallet_address("cust-001", SupportedBlockchain.BTC)  # type: ignore[attr-defined]

    assert type(exc_info.value).__name__ == "CryptoLedgerError"
    assert exc_info.value.code == "http_409"  # type: ignore[attr-defined]


# ── create_tx ─────────────────────────────────────────────────────────────────


def test_create_tx_sends_post_to_transactions(adapter: object, mock_http: MagicMock) -> None:
    mock_http.request.return_value = _make_resp(_TX_PENDING)

    adapter.create_tx(_make_tx_request())  # type: ignore[attr-defined]

    post_call = mock_http.request.call_args
    assert post_call[0][0] == "POST"
    assert post_call[0][1].endswith("/v1/transactions")


def test_create_tx_sends_external_id_for_idempotency(adapter: object, mock_http: MagicMock) -> None:
    mock_http.request.return_value = _make_resp(_TX_PENDING)

    adapter.create_tx(_make_tx_request())  # type: ignore[attr-defined]

    import json

    body_bytes = mock_http.request.call_args[1]["content"]
    body = json.loads(body_bytes.decode())
    assert body["externalId"] == "tx-idem-001"


def test_create_tx_returns_crypto_transaction_result(adapter: object, mock_http: MagicMock) -> None:
    mock_http.request.return_value = _make_resp(_TX_PENDING)

    result = adapter.create_tx(_make_tx_request())  # type: ignore[attr-defined]

    assert type(result).__name__ == "CryptoTransactionResult"
    assert result.tx_id == "tx-idem-001"
    assert result.status == CryptoTransactionStatus.PENDING
    assert result.tx_hash is None


def test_create_tx_maps_confirmed_status(adapter: object, mock_http: MagicMock) -> None:
    mock_http.request.return_value = _make_resp(_TX_CONFIRMED)

    result = adapter.create_tx(_make_tx_request())  # type: ignore[attr-defined]

    assert result.status == CryptoTransactionStatus.CONFIRMED
    assert result.tx_hash == "deadbeef1234"


def test_create_tx_maps_approved_to_confirmed(adapter: object, mock_http: MagicMock) -> None:
    mock_http.request.return_value = _make_resp(_TX_APPROVED)

    result = adapter.create_tx(_make_tx_request())  # type: ignore[attr-defined]

    assert result.status == CryptoTransactionStatus.CONFIRMED


def test_create_tx_maps_failed_status(adapter: object, mock_http: MagicMock) -> None:
    mock_http.request.return_value = _make_resp(_TX_FAILED)

    result = adapter.create_tx(_make_tx_request())  # type: ignore[attr-defined]

    assert result.status == CryptoTransactionStatus.FAILED


def test_create_tx_amount_preserved_as_decimal(adapter: object, mock_http: MagicMock) -> None:
    mock_http.request.return_value = _make_resp(_TX_PENDING)

    result = adapter.create_tx(_make_tx_request(amount="10.00"))  # type: ignore[attr-defined]

    assert isinstance(result.amount, Decimal)
    assert result.amount == Decimal("10.00")


def test_create_tx_raises_on_http_error(adapter: object, mock_http: MagicMock) -> None:
    err_resp = _make_resp({}, status_code=422)
    err_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "unprocessable", request=MagicMock(), response=err_resp
    )
    mock_http.request.return_value = err_resp

    with pytest.raises(Exception) as exc_info:
        adapter.create_tx(_make_tx_request())  # type: ignore[attr-defined]

    assert type(exc_info.value).__name__ == "CryptoLedgerError"
    assert exc_info.value.code == "http_422"  # type: ignore[attr-defined]


# ── get_fee_estimate ──────────────────────────────────────────────────────────


def test_get_fee_estimate_returns_crypto_fee_estimate(adapter: object) -> None:
    result = adapter.get_fee_estimate(SupportedBlockchain.BTC, Decimal("1.0"))  # type: ignore[attr-defined]

    assert type(result).__name__ == "CryptoFeeEstimate"
    assert result.blockchain == SupportedBlockchain.BTC
    assert result.priority == FeePriority.MEDIUM
    assert isinstance(result.fee, Decimal)


def test_get_fee_estimate_deterministic_no_http_call(adapter: object, mock_http: MagicMock) -> None:
    adapter.get_fee_estimate(SupportedBlockchain.ETH, Decimal("0.5"))  # type: ignore[attr-defined]

    mock_http.request.assert_not_called()


def test_get_fee_estimate_btc_medium_fee(adapter: object) -> None:
    result = adapter.get_fee_estimate(SupportedBlockchain.BTC, Decimal("1.0"))  # type: ignore[attr-defined]

    assert result.fee == Decimal("0.00005")
    assert result.currency == "BTC"
    assert result.estimated_confirmation_blocks == 3


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
