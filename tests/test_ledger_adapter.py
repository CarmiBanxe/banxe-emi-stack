"""
tests/test_ledger_adapter.py — MidazLedgerAdapter + StubLedgerAdapter tests
S13-01 | CASS 7.15 | I-05 (Decimal only) | banxe-emi-stack

Tests MidazLedgerAdapter using unittest.mock to patch httpx.AsyncClient,
so no live Midaz instance is required.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from services.ledger.midaz_adapter import (
    MidazLedgerAdapter,
    StubLedgerAdapter,
    TransactionRequest,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

ORG = "org-001"
LEDGER = "ledger-001"
ACCOUNT = "acct-001"


def _make_adapter(token: str = "test-token") -> MidazLedgerAdapter:
    return MidazLedgerAdapter(base_url="http://test-midaz:8095", token=token, timeout=5.0)


def _mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
    """Build a mock httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        import httpx

        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    return resp


# ── StubLedgerAdapter ─────────────────────────────────────────────────────────


class TestStubLedgerAdapter:
    def test_get_balance_known_account(self):
        stub = StubLedgerAdapter({ACCOUNT: Decimal("5000.00")})
        assert stub.get_balance(ORG, LEDGER, ACCOUNT) == Decimal("5000.00")

    def test_get_balance_unknown_returns_zero(self):
        stub = StubLedgerAdapter()
        assert stub.get_balance(ORG, LEDGER, "unknown") == Decimal("0")

    def test_get_balance_is_decimal(self):
        stub = StubLedgerAdapter({ACCOUNT: Decimal("1234.56")})
        result = stub.get_balance(ORG, LEDGER, ACCOUNT)
        assert isinstance(result, Decimal), "Balance must be Decimal (I-05)"

    def test_create_transaction_returns_record(self):
        stub = StubLedgerAdapter()
        req = TransactionRequest(amount_gbp=Decimal("100.00"), description="Test payment")
        record = stub.create_transaction(ORG, LEDGER, req)
        assert record is not None
        assert record.amount_gbp == Decimal("100.00")

    def test_create_transaction_amount_is_decimal(self):
        stub = StubLedgerAdapter()
        req = TransactionRequest(amount_gbp=Decimal("99.99"), description="Test")
        record = stub.create_transaction(ORG, LEDGER, req)
        assert isinstance(record.amount_gbp, Decimal), "Amount must be Decimal (I-05)"

    def test_create_transaction_sequential_ids(self):
        stub = StubLedgerAdapter()
        req = TransactionRequest(amount_gbp=Decimal("10.00"), description="A")
        r1 = stub.create_transaction(ORG, LEDGER, req)
        r2 = stub.create_transaction(ORG, LEDGER, req)
        assert r1.transaction_id != r2.transaction_id

    def test_create_transaction_status_approved(self):
        stub = StubLedgerAdapter()
        req = TransactionRequest(amount_gbp=Decimal("50.00"), description="B")
        record = stub.create_transaction(ORG, LEDGER, req)
        assert record.status == "APPROVED"

    def test_list_transactions_empty_initially(self):
        stub = StubLedgerAdapter()
        txns = stub.list_transactions(ORG, LEDGER, ACCOUNT)
        assert txns == []

    def test_list_transactions_after_create(self):
        stub = StubLedgerAdapter()
        req = TransactionRequest(amount_gbp=Decimal("25.00"), description="C")
        stub.create_transaction(ORG, LEDGER, req)
        txns = stub.list_transactions(ORG, LEDGER, ACCOUNT)
        assert len(txns) == 1

    def test_list_transactions_newest_first(self):
        stub = StubLedgerAdapter()
        for i in range(3):
            stub.create_transaction(
                ORG,
                LEDGER,
                TransactionRequest(amount_gbp=Decimal(str(i + 1)), description=f"tx{i}"),
            )
        txns = stub.list_transactions(ORG, LEDGER, ACCOUNT)
        # reversed = newest first
        assert txns[0].transaction_id == "stub-tx-0003"


# ── MidazLedgerAdapter — _extract_gbp_balance ─────────────────────────────────


class TestMidazExtractBalance:
    def test_extracts_gbp_from_items(self):
        adapter = _make_adapter()
        data = {"items": [{"assetCode": "GBP", "available": 10000000}]}
        result = adapter._extract_gbp_balance(data, ACCOUNT)
        assert result == Decimal("100000.00")

    def test_extracts_gbp_lowercase(self):
        adapter = _make_adapter()
        data = {"items": [{"assetCode": "gbp", "available": 5000}]}
        result = adapter._extract_gbp_balance(data, ACCOUNT)
        assert result == Decimal("50.00")

    def test_no_gbp_returns_zero(self):
        adapter = _make_adapter()
        data = {"items": [{"assetCode": "USD", "available": 9999}]}
        result = adapter._extract_gbp_balance(data, ACCOUNT)
        assert result == Decimal("0")

    def test_empty_items_returns_zero(self):
        adapter = _make_adapter()
        data = {"items": []}
        result = adapter._extract_gbp_balance(data, ACCOUNT)
        assert result == Decimal("0")

    def test_result_is_decimal(self):
        adapter = _make_adapter()
        data = {"items": [{"assetCode": "GBP", "available": 12345}]}
        result = adapter._extract_gbp_balance(data, ACCOUNT)
        assert isinstance(result, Decimal), "Balance must be Decimal (I-05)"


# ── MidazLedgerAdapter — _parse_transaction ───────────────────────────────────


class TestMidazParseTransaction:
    def test_parses_amount_from_pence(self):
        adapter = _make_adapter()
        data = {
            "id": "tx-abc",
            "amount": 9999,
            "assetCode": "GBP",
            "description": "Test",
            "status": "APPROVED",
            "createdAt": "2026-04-13T12:00:00Z",
        }
        record = adapter._parse_transaction(data)
        assert record.amount_gbp == Decimal("99.99")

    def test_parses_transaction_id(self):
        adapter = _make_adapter()
        data = {
            "id": "tx-xyz",
            "amount": 100,
            "assetCode": "GBP",
            "description": "D",
            "status": "PENDING",
            "createdAt": "2026-04-13T12:00:00Z",
        }
        record = adapter._parse_transaction(data)
        assert record.transaction_id == "tx-xyz"

    def test_amount_is_decimal(self):
        adapter = _make_adapter()
        data = {
            "id": "t",
            "amount": 50000,
            "assetCode": "GBP",
            "description": "E",
            "status": "APPROVED",
            "createdAt": "2026-04-13T00:00:00Z",
        }
        record = adapter._parse_transaction(data)
        assert isinstance(record.amount_gbp, Decimal)

    def test_fallback_created_at_on_bad_date(self):
        adapter = _make_adapter()
        data = {
            "id": "t",
            "amount": 100,
            "assetCode": "GBP",
            "description": "F",
            "status": "APPROVED",
            "createdAt": "not-a-date",
        }
        record = adapter._parse_transaction(data)
        assert isinstance(record.created_at, datetime)

    def test_external_id_parsed(self):
        adapter = _make_adapter()
        data = {
            "id": "t",
            "amount": 100,
            "assetCode": "GBP",
            "description": "G",
            "status": "APPROVED",
            "createdAt": "2026-04-13T00:00:00Z",
            "externalId": "PAY-12345",
        }
        record = adapter._parse_transaction(data)
        assert record.external_id == "PAY-12345"


# ── MidazLedgerAdapter — HTTP calls via mock ──────────────────────────────────


class TestMidazAdapterHTTP:
    def test_get_balance_happy_path(self):
        """get_balance fetches from Midaz and returns Decimal (I-05)."""
        adapter = _make_adapter()
        mock_resp = _mock_response({"items": [{"assetCode": "GBP", "available": 12500000}]})

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__.return_value = mock_client
            mock_client.get = AsyncMock(return_value=mock_resp)
            result = adapter.get_balance(ORG, LEDGER, ACCOUNT)

        assert result == Decimal("125000.00")
        assert isinstance(result, Decimal)

    def test_get_balance_http_error_returns_zero(self):
        """On HTTP error, get_balance returns Decimal("0") — safe fallback."""
        adapter = _make_adapter()
        mock_resp = _mock_response({}, status_code=500)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__.return_value = mock_client
            mock_client.get = AsyncMock(return_value=mock_resp)
            result = adapter.get_balance(ORG, LEDGER, ACCOUNT)

        assert result == Decimal("0")

    def test_get_balance_network_error_returns_zero(self):
        """On network failure, get_balance returns Decimal("0")."""
        adapter = _make_adapter()
        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__.return_value = mock_client
            mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
            result = adapter.get_balance(ORG, LEDGER, ACCOUNT)

        assert result == Decimal("0")

    def test_create_transaction_happy_path(self):
        """create_transaction POSTs to Midaz and returns TransactionRecord."""

        adapter = _make_adapter()
        mock_resp = _mock_response(
            {
                "id": "tx-live-001",
                "amount": 10000,
                "assetCode": "GBP",
                "description": "Test payment",
                "status": "APPROVED",
                "createdAt": "2026-04-13T12:00:00Z",
                "externalId": "ref-001",
            }
        )
        req = TransactionRequest(
            amount_gbp=Decimal("100.00"),
            description="Test payment",
            external_id="ref-001",
        )

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__.return_value = mock_client
            mock_client.post = AsyncMock(return_value=mock_resp)
            record = adapter.create_transaction(ORG, LEDGER, req)

        assert record is not None
        assert record.transaction_id == "tx-live-001"
        assert record.amount_gbp == Decimal("100.00")
        assert isinstance(record.amount_gbp, Decimal)

    def test_create_transaction_error_returns_none(self):
        """On HTTP error, create_transaction returns None (log + safe fallback)."""

        adapter = _make_adapter()
        mock_resp = _mock_response({}, status_code=400)
        req = TransactionRequest(amount_gbp=Decimal("50.00"), description="Bad")

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__.return_value = mock_client
            mock_client.post = AsyncMock(return_value=mock_resp)
            record = adapter.create_transaction(ORG, LEDGER, req)

        assert record is None

    def test_list_transactions_happy_path(self):
        """list_transactions fetches from Midaz and returns list of TransactionRecord."""
        adapter = _make_adapter()
        mock_resp = _mock_response(
            {
                "items": [
                    {
                        "id": "tx-a",
                        "amount": 5000,
                        "assetCode": "GBP",
                        "description": "Payment A",
                        "status": "APPROVED",
                        "createdAt": "2026-04-13T10:00:00Z",
                    },
                    {
                        "id": "tx-b",
                        "amount": 2500,
                        "assetCode": "GBP",
                        "description": "Payment B",
                        "status": "APPROVED",
                        "createdAt": "2026-04-12T10:00:00Z",
                    },
                ]
            }
        )

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__.return_value = mock_client
            mock_client.get = AsyncMock(return_value=mock_resp)
            txns = adapter.list_transactions(ORG, LEDGER, ACCOUNT)

        assert len(txns) == 2
        assert txns[0].transaction_id == "tx-a"
        assert txns[0].amount_gbp == Decimal("50.00")

    def test_list_transactions_error_returns_empty(self):
        """On HTTP error, list_transactions returns []."""

        adapter = _make_adapter()
        mock_resp = _mock_response({}, status_code=503)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__.return_value = mock_client
            mock_client.get = AsyncMock(return_value=mock_resp)
            txns = adapter.list_transactions(ORG, LEDGER, ACCOUNT)

        assert txns == []

    def test_adapter_sets_auth_header_when_token_set(self):
        """Authorization header is set when token provided."""
        adapter = MidazLedgerAdapter(
            base_url="http://test:8095", token="my-secret-token", timeout=5.0
        )
        assert adapter._headers.get("Authorization") == "Bearer my-secret-token"

    def test_adapter_no_auth_header_without_token(self):
        """No Authorization header when token is empty."""
        adapter = MidazLedgerAdapter(base_url="http://test:8095", token="", timeout=5.0)
        assert "Authorization" not in adapter._headers

    def test_transaction_request_amount_is_decimal(self):
        """TransactionRequest enforces Decimal (I-05)."""
        req = TransactionRequest(amount_gbp=Decimal("500.00"), description="Test")
        assert isinstance(req.amount_gbp, Decimal)

    def test_list_transactions_empty_response(self):
        """Empty items list returns []."""
        adapter = _make_adapter()
        mock_resp = _mock_response({"items": []})

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__.return_value = mock_client
            mock_client.get = AsyncMock(return_value=mock_resp)
            txns = adapter.list_transactions(ORG, LEDGER, ACCOUNT)

        assert txns == []


import httpx  # noqa: E402 — needed for side_effect references above
