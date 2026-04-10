"""
tests/test_api_statements.py — Statement API endpoint tests
GET /v1/accounts/{account_id}/statement      — JSON
GET /v1/accounts/{account_id}/statement/csv  — CSV download

FCA PS7/24 | CASS 15 | banxe-emi-stack
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from api.deps import get_statement_service
from api.main import app
from services.statements.statement_service import (
    AccountStatementService,
    InMemoryTransactionRepository,
    TransactionLine,
)

client = TestClient(app)

# ── Fixtures ───────────────────────────────────────────────────────────────────


def _tx(
    tx_date: date,
    description: str,
    debit: str | None = None,
    credit: str | None = None,
    balance_after: str = "0.00",
    ref: str = "ref-001",
    tx_id: str = "tx-0001",
) -> TransactionLine:
    return TransactionLine(
        date=tx_date,
        description=description,
        reference=ref,
        debit=Decimal(debit) if debit else None,
        credit=Decimal(credit) if credit else None,
        balance_after=Decimal(balance_after),
        transaction_id=tx_id,
    )


_MARCH_TXS = [
    _tx(
        date(2026, 3, 1),
        "Opening deposit",
        credit="5000.00",
        balance_after="5000.00",
        tx_id="tx-0001",
    ),
    _tx(
        date(2026, 3, 10),
        "Payment to vendor",
        debit="500.00",
        balance_after="4500.00",
        tx_id="tx-0002",
    ),
    _tx(
        date(2026, 3, 15),
        "Salary credit",
        credit="3000.00",
        balance_after="7500.00",
        tx_id="tx-0003",
    ),
    _tx(
        date(2026, 3, 28), "Rent payment", debit="1200.00", balance_after="6300.00", tx_id="tx-0004"
    ),
]

BASE_PARAMS = {
    "customer_id": "cust-001",
    "currency": "GBP",
    "from": "2026-03-01",
    "to": "2026-03-31",
}


@pytest.fixture(autouse=True)
def inject_statement_service():
    """Override statement service with pre-loaded March transactions."""
    repo = InMemoryTransactionRepository(
        transactions=_MARCH_TXS,
        opening_balance=Decimal("0.00"),
    )
    svc = AccountStatementService(repo=repo)
    app.dependency_overrides[get_statement_service] = lambda: svc
    yield svc
    app.dependency_overrides.clear()


# ── JSON endpoint — happy path ─────────────────────────────────────────────────


class TestStatementJSON:
    def test_returns_200(self):
        resp = client.get("/v1/accounts/acc-001/statement", params=BASE_PARAMS)
        assert resp.status_code == 200

    def test_statement_id_present(self):
        resp = client.get("/v1/accounts/acc-001/statement", params=BASE_PARAMS)
        assert resp.json()["statement_id"].startswith("stmt-")

    def test_account_id_matches_path(self):
        resp = client.get("/v1/accounts/acc-001/statement", params=BASE_PARAMS)
        assert resp.json()["account_id"] == "acc-001"

    def test_customer_id_matches_param(self):
        resp = client.get("/v1/accounts/acc-001/statement", params=BASE_PARAMS)
        assert resp.json()["customer_id"] == "cust-001"

    def test_currency_uppercased(self):
        params = {**BASE_PARAMS, "currency": "gbp"}
        resp = client.get("/v1/accounts/acc-001/statement", params=params)
        assert resp.json()["currency"] == "GBP"

    def test_period_start_end(self):
        resp = client.get("/v1/accounts/acc-001/statement", params=BASE_PARAMS)
        body = resp.json()
        assert body["period_start"] == "2026-03-01"
        assert body["period_end"] == "2026-03-31"

    def test_transaction_count(self):
        resp = client.get("/v1/accounts/acc-001/statement", params=BASE_PARAMS)
        assert resp.json()["transaction_count"] == 4

    def test_total_credits(self):
        resp = client.get("/v1/accounts/acc-001/statement", params=BASE_PARAMS)
        assert resp.json()["total_credits"] == "8000.00"

    def test_total_debits(self):
        resp = client.get("/v1/accounts/acc-001/statement", params=BASE_PARAMS)
        assert resp.json()["total_debits"] == "1700.00"

    def test_net_movement(self):
        resp = client.get("/v1/accounts/acc-001/statement", params=BASE_PARAMS)
        assert resp.json()["net_movement"] == "6300.00"

    def test_closing_balance(self):
        resp = client.get("/v1/accounts/acc-001/statement", params=BASE_PARAMS)
        assert resp.json()["closing_balance"] == "6300.00"

    def test_amounts_are_strings(self):
        resp = client.get("/v1/accounts/acc-001/statement", params=BASE_PARAMS)
        body = resp.json()
        # I-05: never float
        assert isinstance(body["closing_balance"], str)
        assert isinstance(body["total_debits"], str)
        assert isinstance(body["total_credits"], str)
        assert isinstance(body["net_movement"], str)

    def test_transactions_list_present(self):
        resp = client.get("/v1/accounts/acc-001/statement", params=BASE_PARAMS)
        txs = resp.json()["transactions"]
        assert isinstance(txs, list)
        assert len(txs) == 4

    def test_transaction_fields(self):
        resp = client.get("/v1/accounts/acc-001/statement", params=BASE_PARAMS)
        tx = resp.json()["transactions"][0]
        for field in ["date", "description", "reference", "balance_after", "transaction_id"]:
            assert field in tx

    def test_transaction_debit_credit_mutually_exclusive(self):
        resp = client.get("/v1/accounts/acc-001/statement", params=BASE_PARAMS)
        txs = resp.json()["transactions"]
        for tx in txs:
            assert not (tx["debit"] is not None and tx["credit"] is not None), (
                f"tx {tx['transaction_id']} has both debit and credit"
            )

    def test_transaction_amounts_are_strings(self):
        resp = client.get("/v1/accounts/acc-001/statement", params=BASE_PARAMS)
        txs = resp.json()["transactions"]
        for tx in txs:
            if tx["debit"] is not None:
                assert isinstance(tx["debit"], str)
            if tx["credit"] is not None:
                assert isinstance(tx["credit"], str)
            assert isinstance(tx["balance_after"], str)

    def test_generated_at_present(self):
        resp = client.get("/v1/accounts/acc-001/statement", params=BASE_PARAMS)
        assert "generated_at" in resp.json()

    def test_empty_period_returns_zero_transactions(self):
        params = {**BASE_PARAMS, "from": "2026-01-01", "to": "2026-01-31"}
        resp = client.get("/v1/accounts/acc-001/statement", params=params)
        assert resp.status_code == 200
        assert resp.json()["transaction_count"] == 0
        assert resp.json()["total_credits"] == "0"
        assert resp.json()["total_debits"] == "0"

    def test_partial_period_filters_correctly(self):
        params = {**BASE_PARAMS, "from": "2026-03-10", "to": "2026-03-15"}
        resp = client.get("/v1/accounts/acc-001/statement", params=params)
        assert resp.status_code == 200
        assert resp.json()["transaction_count"] == 2


# ── JSON endpoint — validation errors ─────────────────────────────────────────


class TestStatementJSONValidation:
    def test_missing_customer_id_returns_422(self):
        params = {k: v for k, v in BASE_PARAMS.items() if k != "customer_id"}
        resp = client.get("/v1/accounts/acc-001/statement", params=params)
        assert resp.status_code == 422

    def test_missing_from_returns_422(self):
        params = {k: v for k, v in BASE_PARAMS.items() if k != "from"}
        resp = client.get("/v1/accounts/acc-001/statement", params=params)
        assert resp.status_code == 422

    def test_missing_to_returns_422(self):
        params = {k: v for k, v in BASE_PARAMS.items() if k != "to"}
        resp = client.get("/v1/accounts/acc-001/statement", params=params)
        assert resp.status_code == 422

    def test_invalid_date_format_returns_422(self):
        params = {**BASE_PARAMS, "from": "01/03/2026"}
        resp = client.get("/v1/accounts/acc-001/statement", params=params)
        assert resp.status_code == 422

    def test_to_before_from_returns_422(self):
        params = {**BASE_PARAMS, "from": "2026-03-31", "to": "2026-03-01"}
        resp = client.get("/v1/accounts/acc-001/statement", params=params)
        assert resp.status_code == 422

    def test_period_over_366_days_returns_422(self):
        params = {**BASE_PARAMS, "from": "2024-01-01", "to": "2026-03-31"}
        resp = client.get("/v1/accounts/acc-001/statement", params=params)
        assert resp.status_code == 422

    def test_exactly_366_days_accepted(self):
        params = {**BASE_PARAMS, "from": "2025-03-31", "to": "2026-03-31"}
        resp = client.get("/v1/accounts/acc-001/statement", params=params)
        assert resp.status_code == 200

    def test_same_day_period_accepted(self):
        params = {**BASE_PARAMS, "from": "2026-03-15", "to": "2026-03-15"}
        resp = client.get("/v1/accounts/acc-001/statement", params=params)
        assert resp.status_code == 200
        assert resp.json()["transaction_count"] == 1  # only 2026-03-15 tx


# ── CSV endpoint — happy path ──────────────────────────────────────────────────


class TestStatementCSV:
    def test_returns_200(self):
        resp = client.get("/v1/accounts/acc-001/statement/csv", params=BASE_PARAMS)
        assert resp.status_code == 200

    def test_content_type_csv(self):
        resp = client.get("/v1/accounts/acc-001/statement/csv", params=BASE_PARAMS)
        assert "text/csv" in resp.headers["content-type"]

    def test_content_disposition_attachment(self):
        resp = client.get("/v1/accounts/acc-001/statement/csv", params=BASE_PARAMS)
        assert "attachment" in resp.headers["content-disposition"]
        assert "statement_acc-001_202603.csv" in resp.headers["content-disposition"]

    def test_csv_is_bytes(self):
        resp = client.get("/v1/accounts/acc-001/statement/csv", params=BASE_PARAMS)
        assert isinstance(resp.content, bytes)
        assert len(resp.content) > 0

    def test_csv_has_header_row(self):
        resp = client.get("/v1/accounts/acc-001/statement/csv", params=BASE_PARAMS)
        text = resp.content.decode("utf-8")
        assert "Date" in text
        assert "Description" in text
        assert "Balance" in text

    def test_csv_contains_transaction_descriptions(self):
        resp = client.get("/v1/accounts/acc-001/statement/csv", params=BASE_PARAMS)
        text = resp.content.decode("utf-8")
        assert "Opening deposit" in text
        assert "Salary credit" in text
        assert "Rent payment" in text

    def test_csv_has_summary_rows(self):
        resp = client.get("/v1/accounts/acc-001/statement/csv", params=BASE_PARAMS)
        text = resp.content.decode("utf-8")
        assert "Opening Balance" in text
        assert "Closing Balance" in text

    def test_csv_amounts_correct(self):
        resp = client.get("/v1/accounts/acc-001/statement/csv", params=BASE_PARAMS)
        text = resp.content.decode("utf-8")
        assert "5000.00" in text
        assert "3000.00" in text
        assert "1200.00" in text

    def test_csv_empty_period(self):
        params = {**BASE_PARAMS, "from": "2026-01-01", "to": "2026-01-31"}
        resp = client.get("/v1/accounts/acc-001/statement/csv", params=params)
        assert resp.status_code == 200
        text = resp.content.decode("utf-8")
        assert "Date" in text  # header still present


# ── CSV endpoint — validation errors ──────────────────────────────────────────


class TestStatementCSVValidation:
    def test_to_before_from_returns_422(self):
        params = {**BASE_PARAMS, "from": "2026-03-31", "to": "2026-03-01"}
        resp = client.get("/v1/accounts/acc-001/statement/csv", params=params)
        assert resp.status_code == 422

    def test_period_over_366_days_returns_422(self):
        params = {**BASE_PARAMS, "from": "2024-01-01", "to": "2026-03-31"}
        resp = client.get("/v1/accounts/acc-001/statement/csv", params=params)
        assert resp.status_code == 422

    def test_missing_customer_id_returns_422(self):
        params = {k: v for k, v in BASE_PARAMS.items() if k != "customer_id"}
        resp = client.get("/v1/accounts/acc-001/statement/csv", params=params)
        assert resp.status_code == 422


# ── Different account IDs ──────────────────────────────────────────────────────


class TestStatementAccountId:
    def test_different_account_ids_return_same_data(self):
        """InMemoryRepo returns all transactions regardless of account_id."""
        resp1 = client.get("/v1/accounts/acc-001/statement", params=BASE_PARAMS)
        resp2 = client.get("/v1/accounts/acc-999/statement", params=BASE_PARAMS)
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.json()["account_id"] == "acc-001"
        assert resp2.json()["account_id"] == "acc-999"

    def test_account_id_reflected_in_csv_filename(self):
        resp = client.get("/v1/accounts/acc-XYZ/statement/csv", params=BASE_PARAMS)
        assert "acc-XYZ" in resp.headers["content-disposition"]
