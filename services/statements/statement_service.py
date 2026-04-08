"""
statement_service.py — Account Statement Service (PDF/CSV)
S17-07: Monthly client statement generation
FCA: CASS 15 / FCA PS7/24 — client statement obligations
Pattern: Geniusto v5 "Printed Forms / CSV export"

WHY THIS FILE EXISTS
--------------------
FCA requires EMIs to provide monthly account statements to clients.
FIN060 covers safeguarding reporting to FCA; this covers CLIENT statements.

Generates:
  1. CSV: transaction history for an account + period
  2. PDF: formatted statement (WeasyPrint — same as FIN060)
  3. Balance summary: opening/closing/available/pending

FCA obligations:
  - FCA PS7/24: statement must be provided monthly (or on request)
  - CASS 15: client money statement details
  - UK GDPR Art.5: only include data necessary for the statement period
"""
from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Optional, Protocol

logger = logging.getLogger(__name__)


# ── Domain types ───────────────────────────────────────────────────────────────

class StatementFormat(str, Enum):
    CSV = "CSV"
    PDF = "PDF"
    JSON = "JSON"


@dataclass(frozen=True)
class TransactionLine:
    """One transaction line in a client statement."""
    date: date
    description: str
    reference: str
    debit: Optional[Decimal]        # None if credit
    credit: Optional[Decimal]       # None if debit
    balance_after: Decimal
    transaction_id: str

    @property
    def amount(self) -> Decimal:
        """Signed amount: negative = debit, positive = credit."""
        if self.credit is not None:
            return self.credit
        return -(self.debit or Decimal("0"))


@dataclass
class AccountStatement:
    """
    Monthly account statement — one customer account, one period.
    Generated on-demand or by monthly cron.
    """
    statement_id: str
    customer_id: str
    account_id: str
    currency: str
    period_start: date
    period_end: date
    opening_balance: Decimal
    closing_balance: Decimal
    total_debits: Decimal
    total_credits: Decimal
    transaction_count: int
    transactions: list[TransactionLine]
    generated_at: datetime

    @property
    def net_movement(self) -> Decimal:
        return self.total_credits - self.total_debits

    def to_csv(self) -> bytes:
        """Generate CSV bytes — client-downloadable."""
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "Date", "Description", "Reference",
            "Debit", "Credit", "Balance",
        ])
        for tx in self.transactions:
            writer.writerow([
                tx.date.isoformat(),
                tx.description,
                tx.reference,
                str(tx.debit) if tx.debit else "",
                str(tx.credit) if tx.credit else "",
                str(tx.balance_after),
            ])
        # Summary footer
        writer.writerow([])
        writer.writerow(["Opening Balance", "", "", "", "", str(self.opening_balance)])
        writer.writerow(["Closing Balance", "", "", "", "", str(self.closing_balance)])
        writer.writerow(["Total Debits", "", "", str(self.total_debits), "", ""])
        writer.writerow(["Total Credits", "", "", "", str(self.total_credits), ""])
        return buf.getvalue().encode("utf-8")

    def to_dict(self) -> dict:
        return {
            "statement_id": self.statement_id,
            "customer_id": self.customer_id,
            "account_id": self.account_id,
            "currency": self.currency,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "opening_balance": str(self.opening_balance),
            "closing_balance": str(self.closing_balance),
            "total_debits": str(self.total_debits),
            "total_credits": str(self.total_credits),
            "transaction_count": self.transaction_count,
            "net_movement": str(self.net_movement),
            "generated_at": self.generated_at.isoformat(),
        }


# ── Transaction repository protocol ───────────────────────────────────────────

class TransactionRepository(Protocol):
    def get_transactions(
        self,
        account_id: str,
        period_start: date,
        period_end: date,
    ) -> list[TransactionLine]: ...

    def get_opening_balance(
        self,
        account_id: str,
        as_of: date,
    ) -> Decimal: ...


# ── In-memory repository ───────────────────────────────────────────────────────

class InMemoryTransactionRepository:
    """Pre-loaded transaction list for tests."""

    def __init__(
        self,
        transactions: Optional[list[TransactionLine]] = None,
        opening_balance: Decimal = Decimal("0"),
    ) -> None:
        self._txs = transactions or []
        self._opening = opening_balance

    def get_transactions(self, account_id: str, period_start: date, period_end: date) -> list[TransactionLine]:
        return [
            tx for tx in self._txs
            if period_start <= tx.date <= period_end
        ]

    def get_opening_balance(self, account_id: str, as_of: date) -> Decimal:
        return self._opening


# ── Statement service ──────────────────────────────────────────────────────────

class AccountStatementService:
    """
    Generates monthly account statements for client download.

    Usage:
        svc = AccountStatementService(repo=InMemoryTransactionRepository(...))
        stmt = svc.generate(
            customer_id="cust-001",
            account_id="acc-001",
            currency="GBP",
            period_start=date(2026, 3, 1),
            period_end=date(2026, 3, 31),
        )
        csv_bytes = stmt.to_csv()
    """

    def __init__(self, repo: TransactionRepository) -> None:
        self._repo = repo

    def generate(
        self,
        customer_id: str,
        account_id: str,
        currency: str,
        period_start: date,
        period_end: date,
    ) -> AccountStatement:
        import uuid
        transactions = self._repo.get_transactions(account_id, period_start, period_end)
        opening = self._repo.get_opening_balance(account_id, period_start)

        total_debits = sum(
            (tx.debit or Decimal("0")) for tx in transactions
        )
        total_credits = sum(
            (tx.credit or Decimal("0")) for tx in transactions
        )
        closing = opening + total_credits - total_debits

        logger.info(
            "Statement generated: customer=%s account=%s period=%s..%s txs=%d",
            customer_id, account_id, period_start, period_end, len(transactions),
        )

        return AccountStatement(
            statement_id=f"stmt-{uuid.uuid4().hex[:12]}",
            customer_id=customer_id,
            account_id=account_id,
            currency=currency,
            period_start=period_start,
            period_end=period_end,
            opening_balance=opening,
            closing_balance=closing,
            total_debits=total_debits,
            total_credits=total_credits,
            transaction_count=len(transactions),
            transactions=transactions,
            generated_at=datetime.now(timezone.utc),
        )

    def generate_pdf(self, stmt: AccountStatement, output_dir: Path) -> Path:  # pragma: no cover
        """
        Generate PDF using WeasyPrint (same pattern as FIN060 PDF).
        STATUS: STUB — WeasyPrint installed, template TBD.
        """
        try:
            from weasyprint import HTML  # type: ignore[import]
        except ImportError:
            raise ImportError("Install weasyprint: pip install weasyprint")

        html = self._render_html(stmt)
        output_path = output_dir / f"statement_{stmt.account_id}_{stmt.period_start.strftime('%Y%m')}.pdf"
        output_dir.mkdir(parents=True, exist_ok=True)
        HTML(string=html).write_pdf(str(output_path))
        return output_path

    def _render_html(self, stmt: AccountStatement) -> str:
        rows = "".join(
            f"<tr><td>{tx.date}</td><td>{tx.description}</td>"
            f"<td>{tx.reference}</td>"
            f"<td>{tx.debit or ''}</td><td>{tx.credit or ''}</td>"
            f"<td>{tx.balance_after}</td></tr>"
            for tx in stmt.transactions
        )
        return f"""
        <html><body>
        <h1>Account Statement — {stmt.account_id}</h1>
        <p>Period: {stmt.period_start} to {stmt.period_end}</p>
        <p>Currency: {stmt.currency} | Customer: {stmt.customer_id}</p>
        <table border="1">
          <tr><th>Date</th><th>Description</th><th>Reference</th>
              <th>Debit</th><th>Credit</th><th>Balance</th></tr>
          {rows}
        </table>
        <p>Opening: {stmt.opening_balance} | Closing: {stmt.closing_balance}</p>
        <p>Generated: {stmt.generated_at.isoformat()}</p>
        </body></html>
        """
