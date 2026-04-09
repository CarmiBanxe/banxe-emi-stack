"""
test_statement_service.py — Account Statement Service tests
S17-07: Monthly client PDF/CSV statement
FCA PS7/24 | CASS 15
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from services.statements.statement_service import (
    AccountStatementService,
    InMemoryTransactionRepository,
    TransactionLine,
)

# ── Fixtures ───────────────────────────────────────────────────────────────────


def _tx(
    tx_date: date,
    description: str,
    debit: str | None = None,
    credit: str | None = None,
    balance_after: str = "0",
    ref: str = "ref-001",
) -> TransactionLine:
    return TransactionLine(
        date=tx_date,
        description=description,
        reference=ref,
        debit=Decimal(debit) if debit else None,
        credit=Decimal(credit) if credit else None,
        balance_after=Decimal(balance_after),
        transaction_id=f"tx-{hash(description) % 1000:04d}",
    )


@pytest.fixture
def march_transactions():
    return [
        _tx(date(2026, 3, 1), "Opening deposit", credit="5000.00", balance_after="5000.00"),
        _tx(date(2026, 3, 10), "Payment to vendor", debit="500.00", balance_after="4500.00"),
        _tx(date(2026, 3, 15), "Salary credit", credit="3000.00", balance_after="7500.00"),
        _tx(date(2026, 3, 28), "Rent payment", debit="1200.00", balance_after="6300.00"),
    ]


@pytest.fixture
def repo(march_transactions):
    return InMemoryTransactionRepository(
        transactions=march_transactions,
        opening_balance=Decimal("0.00"),
    )


@pytest.fixture
def svc(repo):
    return AccountStatementService(repo=repo)


@pytest.fixture
def march_stmt(svc):
    return svc.generate(
        customer_id="cust-001",
        account_id="acc-001",
        currency="GBP",
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 31),
    )


# ── Statement generation ───────────────────────────────────────────────────────


class TestStatementGeneration:
    def test_statement_id_assigned(self, march_stmt):
        assert march_stmt.statement_id.startswith("stmt-")

    def test_transaction_count(self, march_stmt):
        assert march_stmt.transaction_count == 4

    def test_total_credits(self, march_stmt):
        assert march_stmt.total_credits == Decimal("8000.00")

    def test_total_debits(self, march_stmt):
        assert march_stmt.total_debits == Decimal("1700.00")

    def test_net_movement(self, march_stmt):
        assert march_stmt.net_movement == Decimal("6300.00")

    def test_closing_balance(self, march_stmt):
        # Opening 0 + credits 8000 - debits 1700 = 6300
        assert march_stmt.closing_balance == Decimal("6300.00")

    def test_currency_set(self, march_stmt):
        assert march_stmt.currency == "GBP"

    def test_generated_at_utc(self, march_stmt):
        assert march_stmt.generated_at.tzinfo is not None

    def test_period_boundaries(self, march_stmt):
        assert march_stmt.period_start == date(2026, 3, 1)
        assert march_stmt.period_end == date(2026, 3, 31)


# ── Period filtering ───────────────────────────────────────────────────────────


class TestPeriodFilter:
    def test_only_march_transactions(self, svc):
        stmt = svc.generate("cust-001", "acc-001", "GBP", date(2026, 3, 10), date(2026, 3, 15))
        assert stmt.transaction_count == 2

    def test_empty_period(self, svc):
        stmt = svc.generate("cust-001", "acc-001", "GBP", date(2026, 1, 1), date(2026, 1, 31))
        assert stmt.transaction_count == 0
        assert stmt.total_credits == Decimal("0")
        assert stmt.total_debits == Decimal("0")


# ── CSV export ─────────────────────────────────────────────────────────────────


class TestCSVExport:
    def test_csv_is_bytes(self, march_stmt):
        csv_data = march_stmt.to_csv()
        assert isinstance(csv_data, bytes)

    def test_csv_has_header(self, march_stmt):
        csv_text = march_stmt.to_csv().decode()
        assert "Date" in csv_text
        assert "Description" in csv_text
        assert "Balance" in csv_text

    def test_csv_has_transaction_rows(self, march_stmt):
        csv_text = march_stmt.to_csv().decode()
        assert "Opening deposit" in csv_text
        assert "Salary credit" in csv_text

    def test_csv_has_summary(self, march_stmt):
        csv_text = march_stmt.to_csv().decode()
        assert "Opening Balance" in csv_text
        assert "Closing Balance" in csv_text

    def test_csv_debit_credit_columns(self, march_stmt):
        csv_text = march_stmt.to_csv().decode()
        assert "500.00" in csv_text  # debit
        assert "3000.00" in csv_text  # credit


# ── JSON / dict export ─────────────────────────────────────────────────────────


class TestDictExport:
    def test_to_dict_keys(self, march_stmt):
        d = march_stmt.to_dict()
        for key in [
            "statement_id",
            "customer_id",
            "account_id",
            "currency",
            "period_start",
            "period_end",
            "opening_balance",
            "closing_balance",
            "total_debits",
            "total_credits",
            "transaction_count",
            "net_movement",
            "generated_at",
        ]:
            assert key in d

    def test_amounts_are_strings(self, march_stmt):
        d = march_stmt.to_dict()
        assert isinstance(d["closing_balance"], str)
        assert isinstance(d["total_debits"], str)

    def test_transaction_count_int(self, march_stmt):
        d = march_stmt.to_dict()
        assert isinstance(d["transaction_count"], int)


# ── Transaction line ───────────────────────────────────────────────────────────


class TestTransactionLine:
    def test_amount_credit_positive(self):
        tx = _tx(date(2026, 3, 1), "credit", credit="100.00", balance_after="100.00")
        assert tx.amount == Decimal("100.00")

    def test_amount_debit_negative(self):
        tx = _tx(date(2026, 3, 1), "debit", debit="50.00", balance_after="50.00")
        assert tx.amount == Decimal("-50.00")
