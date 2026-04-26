"""
services/client_statements/statement_generator.py
PDF/CSV/JSON client statement generation (IL-CST-01).
Data sources: Midaz ledger transactions, FX conversions, fees.
I-01: all amounts Decimal strings.
I-24: StatementLog append-only.
BT-013: email_statement() raises NotImplementedError (email service -> P1).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import hashlib
from typing import Protocol

from services.client_statements.statement_models import (
    BalanceSummary,
    FeeBreakdown,
    FXSummary,
    Statement,
    StatementEntry,
    StatementFormat,
)


class StatementDataPort(Protocol):
    """Protocol for statement data sources."""

    def get_transactions(self, customer_id: str, start: str, end: str) -> list[dict]: ...
    def get_opening_balance(self, customer_id: str, date: str) -> str: ...


class InMemoryStatementDataPort:
    """In-memory stub for statement data (Protocol DI)."""

    def get_transactions(self, customer_id: str, start: str, end: str) -> list[dict]:
        return [
            {
                "entry_id": f"ENT_{i:04d}",
                "date": start,
                "description": f"Transaction {i}",
                "amount": str(Decimal("100.00") * (1 if i % 2 == 0 else -1)),
                "currency": "GBP",
                "transaction_type": "transfer",
            }
            for i in range(1, 4)
        ]

    def get_opening_balance(self, customer_id: str, date: str) -> str:
        return "1000.00"


class StatementGenerator:
    """Client statement generator.

    I-01: all amounts as Decimal strings.
    I-24: statement_log is append-only.
    BT-013: email_statement() raises NotImplementedError.
    """

    def __init__(self, data_port: StatementDataPort | None = None) -> None:
        self._data: StatementDataPort = data_port or InMemoryStatementDataPort()
        self._statement_log: list[dict] = []  # I-24 append-only

    def generate(
        self,
        customer_id: str,
        period_start: str,
        period_end: str,
        fmt: StatementFormat = StatementFormat.JSON,
    ) -> Statement:
        stmt_id = (
            "stmt_"
            + hashlib.sha256(f"{customer_id}{period_start}{period_end}".encode()).hexdigest()[:8]
        )
        now = datetime.now(UTC).isoformat()

        txns = self._data.get_transactions(customer_id, period_start, period_end)
        opening_balance = Decimal(self._data.get_opening_balance(customer_id, period_start))

        entries: list[StatementEntry] = []
        running = opening_balance
        total_credits = Decimal("0")
        total_debits = Decimal("0")

        for txn in txns:
            amount = Decimal(txn["amount"])
            running += amount
            if amount > 0:
                total_credits += amount
            else:
                total_debits += abs(amount)
            entries.append(
                StatementEntry(
                    entry_id=txn["entry_id"],
                    date=txn["date"],
                    description=txn["description"],
                    amount=str(amount),
                    running_balance=str(running.quantize(Decimal("0.01"))),
                    currency=txn.get("currency", "GBP"),
                    transaction_type=txn.get("transaction_type", "transfer"),
                )
            )

        closing_balance = running
        balance_summary = BalanceSummary(
            opening_balance=str(opening_balance),
            closing_balance=str(closing_balance.quantize(Decimal("0.01"))),
            total_credits=str(total_credits),
            total_debits=str(total_debits),
        )
        fx_summary = FXSummary(
            conversions_count=0,
            total_converted="0.00",
            currencies=["GBP"],
        )
        fee_breakdown = FeeBreakdown(
            total_fees="0.00",
            by_type={},
        )

        statement = Statement(
            statement_id=stmt_id,
            customer_id=customer_id,
            period_start=period_start,
            period_end=period_end,
            format=fmt,
            entries=entries,
            balance_summary=balance_summary,
            fx_summary=fx_summary,
            fee_breakdown=fee_breakdown,
            generated_at=now,
        )

        self._statement_log.append(
            {
                "event": "statement.generated",
                "statement_id": stmt_id,
                "customer_id": customer_id,
                "period_start": period_start,
                "period_end": period_end,
                "entry_count": len(entries),
                "logged_at": now,
            }
        )
        return statement

    def email_statement(self, statement: Statement, email: str) -> None:
        """BT-013 stub: email delivery requires P1 infrastructure."""
        raise NotImplementedError(
            "BT-013: Email statement delivery not yet implemented. "
            "Requires email service provisioning (P1 item)."
        )

    @property
    def statement_log(self) -> list[dict]:
        return list(self._statement_log)
