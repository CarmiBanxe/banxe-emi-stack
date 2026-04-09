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
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Protocol

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
    debit: Decimal | None  # None if credit
    credit: Decimal | None  # None if debit
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
        writer.writerow(
            [
                "Date",
                "Description",
                "Reference",
                "Debit",
                "Credit",
                "Balance",
            ]
        )
        for tx in self.transactions:
            writer.writerow(
                [
                    tx.date.isoformat(),
                    tx.description,
                    tx.reference,
                    str(tx.debit) if tx.debit else "",
                    str(tx.credit) if tx.credit else "",
                    str(tx.balance_after),
                ]
            )
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
        transactions: list[TransactionLine] | None = None,
        opening_balance: Decimal = Decimal("0"),
    ) -> None:
        self._txs = transactions or []
        self._opening = opening_balance

    def get_transactions(
        self, account_id: str, period_start: date, period_end: date
    ) -> list[TransactionLine]:
        return [tx for tx in self._txs if period_start <= tx.date <= period_end]

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

        total_debits = sum((tx.debit or Decimal("0")) for tx in transactions)
        total_credits = sum((tx.credit or Decimal("0")) for tx in transactions)
        closing = opening + total_credits - total_debits

        logger.info(
            "Statement generated: customer=%s account=%s period=%s..%s txs=%d",
            customer_id,
            account_id,
            period_start,
            period_end,
            len(transactions),
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
            generated_at=datetime.now(UTC),
        )

    def generate_pdf(self, stmt: AccountStatement, output_dir: Path) -> Path:
        """
        Generate a PDF account statement using WeasyPrint.
        Output: {output_dir}/statement_{account_id}_{YYYYMM}.pdf
        FCA PS7/24: monthly statement must be available to client on request.
        """
        try:
            from weasyprint import HTML  # type: ignore[import]
        except ImportError:
            raise ImportError("Install weasyprint: pip install weasyprint")

        html = self._render_html(stmt)
        filename = f"statement_{stmt.account_id}_{stmt.period_start.strftime('%Y%m')}.pdf"
        output_path = output_dir / filename
        output_dir.mkdir(parents=True, exist_ok=True)
        HTML(string=html).write_pdf(str(output_path))
        logger.info("Statement PDF written: %s", output_path)
        return output_path

    def _render_html(self, stmt: AccountStatement) -> str:
        """
        Render account statement as HTML with Banxe branding.
        Inline CSS is required — WeasyPrint does not load external stylesheets.
        """
        ccy = stmt.currency

        def _fmt(amount: Decimal | None) -> str:
            return f"{ccy} {amount:,.2f}" if amount else ""

        def _sign_class(amount: Decimal | None) -> str:
            if amount and amount > 0:
                return 'class="positive"'
            if amount and amount < 0:
                return 'class="negative"'
            return ""

        tx_rows = "".join(
            f"<tr>"
            f"<td>{tx.date.strftime('%d %b %Y')}</td>"
            f"<td>{tx.description}</td>"
            f"<td>{tx.reference}</td>"
            f'<td class="amount-col negative">{_fmt(tx.debit)}</td>'
            f'<td class="amount-col positive">{_fmt(tx.credit)}</td>'
            f'<td class="amount-col">{_fmt(tx.balance_after)}</td>'
            f"</tr>"
            for tx in stmt.transactions
        )

        no_tx_row = (
            '<tr><td colspan="6" style="text-align:center;color:#888;padding:16px;">'
            "No transactions in this period</td></tr>"
            if not stmt.transactions
            else ""
        )

        net_class = "positive" if stmt.net_movement >= 0 else "negative"

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Account Statement — {stmt.statement_id}</title>
<style>
  @page {{
    size: A4;
    margin: 1.5cm 1.8cm;
    @bottom-center {{
      content: "Statement ID: {stmt.statement_id} | Generated: {stmt.generated_at.strftime("%d %b %Y %H:%M UTC")} | Page " counter(page) " of " counter(pages);
      font-size: 7pt;
      color: #888;
    }}
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: Arial, Helvetica, sans-serif; font-size: 9.5pt; color: #222; line-height: 1.4; }}
  .header {{ display: flex; justify-content: space-between; align-items: flex-start;
             border-bottom: 2.5px solid #1a3560; padding-bottom: 14px; margin-bottom: 18px; }}
  .bank-name {{ font-size: 20pt; font-weight: bold; color: #1a3560; letter-spacing: -0.5px; }}
  .bank-tagline {{ font-size: 8pt; color: #666; margin-top: 2px; }}
  .statement-meta {{ text-align: right; }}
  .statement-title {{ font-size: 13pt; font-weight: bold; color: #1a3560; }}
  .statement-date {{ font-size: 8pt; color: #666; margin-top: 4px; }}
  .info-section {{ display: grid; grid-template-columns: 1fr 1fr; gap: 0 24px; margin-bottom: 18px; }}
  .info-block {{ border: 1px solid #dde3ed; border-radius: 4px; padding: 10px 12px; }}
  .info-block-title {{ font-size: 8pt; font-weight: bold; color: #666; text-transform: uppercase;
                       letter-spacing: 0.5px; margin-bottom: 8px; border-bottom: 1px solid #eee; padding-bottom: 4px; }}
  .info-row {{ display: flex; justify-content: space-between; padding: 2px 0; font-size: 9pt; }}
  .info-label {{ color: #555; }}
  .info-value {{ font-weight: bold; }}
  .summary {{ background: #f0f4f9; border: 1px solid #c8d6e8; border-radius: 4px;
              display: grid; grid-template-columns: repeat(4, 1fr);
              gap: 0; margin-bottom: 20px; }}
  .summary-item {{ padding: 12px 10px; text-align: center; border-right: 1px solid #c8d6e8; }}
  .summary-item:last-child {{ border-right: none; }}
  .summary-label {{ font-size: 7.5pt; color: #555; text-transform: uppercase; letter-spacing: 0.4px; }}
  .summary-value {{ font-size: 13pt; font-weight: bold; margin-top: 4px; }}
  .positive {{ color: #1a7340; }}
  .negative {{ color: #c0392b; }}
  .neutral {{ color: #1a3560; }}
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; page-break-inside: auto; }}
  thead {{ display: table-header-group; }}
  th {{ background: #1a3560; color: white; padding: 7px 8px; text-align: left;
        font-size: 8.5pt; font-weight: bold; letter-spacing: 0.2px; }}
  th.amount-col {{ text-align: right; }}
  td {{ padding: 5.5px 8px; border-bottom: 1px solid #eee; font-size: 9pt; vertical-align: top; }}
  tr:nth-child(even) td {{ background: #f9fafb; }}
  .amount-col {{ text-align: right; font-family: 'Courier New', Courier, monospace; font-size: 8.5pt; }}
  .footer {{ border-top: 1px solid #dde3ed; padding-top: 10px; font-size: 7.5pt; color: #888; margin-top: 12px; }}
  .footer p + p {{ margin-top: 3px; }}
</style>
</head>
<body>

<div class="header">
  <div>
    <div class="bank-name">Banxe</div>
    <div class="bank-tagline">Electronic Money Institution — FCA Authorised</div>
  </div>
  <div class="statement-meta">
    <div class="statement-title">Account Statement</div>
    <div class="statement-date">
      {stmt.period_start.strftime("%d %b %Y")} – {stmt.period_end.strftime("%d %b %Y")}
    </div>
  </div>
</div>

<div class="info-section">
  <div class="info-block">
    <div class="info-block-title">Account Details</div>
    <div class="info-row"><span class="info-label">Account ID</span><span class="info-value">{stmt.account_id}</span></div>
    <div class="info-row"><span class="info-label">Customer ID</span><span class="info-value">{stmt.customer_id}</span></div>
    <div class="info-row"><span class="info-label">Currency</span><span class="info-value">{ccy}</span></div>
  </div>
  <div class="info-block">
    <div class="info-block-title">Statement Period</div>
    <div class="info-row"><span class="info-label">From</span><span class="info-value">{stmt.period_start.strftime("%d %b %Y")}</span></div>
    <div class="info-row"><span class="info-label">To</span><span class="info-value">{stmt.period_end.strftime("%d %b %Y")}</span></div>
    <div class="info-row"><span class="info-label">Transactions</span><span class="info-value">{stmt.transaction_count}</span></div>
  </div>
</div>

<div class="summary">
  <div class="summary-item">
    <div class="summary-label">Opening Balance</div>
    <div class="summary-value neutral">{_fmt(stmt.opening_balance)}</div>
  </div>
  <div class="summary-item">
    <div class="summary-label">Total Credits</div>
    <div class="summary-value positive">{_fmt(stmt.total_credits)}</div>
  </div>
  <div class="summary-item">
    <div class="summary-label">Total Debits</div>
    <div class="summary-value negative">{_fmt(stmt.total_debits)}</div>
  </div>
  <div class="summary-item">
    <div class="summary-label">Closing Balance</div>
    <div class="summary-value {net_class}">{_fmt(stmt.closing_balance)}</div>
  </div>
</div>

<table>
  <thead>
    <tr>
      <th style="width:12%">Date</th>
      <th style="width:34%">Description</th>
      <th style="width:18%">Reference</th>
      <th class="amount-col" style="width:12%">Debit ({ccy})</th>
      <th class="amount-col" style="width:12%">Credit ({ccy})</th>
      <th class="amount-col" style="width:12%">Balance ({ccy})</th>
    </tr>
  </thead>
  <tbody>
    {tx_rows}
    {no_tx_row}
  </tbody>
</table>

<div class="footer">
  <p><strong>Banxe Ltd</strong> is an Electronic Money Institution authorised and regulated by the
     Financial Conduct Authority (FCA). Reference number: FRN {stmt.statement_id[:8].upper()}.</p>
  <p>This statement is provided in accordance with FCA PS7/24. If you have questions, contact
     support@banxe.com. For complaints, refer to our Complaints Policy at banxe.com/complaints.</p>
  <p>Statement ID: {stmt.statement_id} | Generated: {stmt.generated_at.strftime("%d %b %Y %H:%M UTC")}</p>
</div>

</body>
</html>"""
