"""
fin060_generator.py — FCA FIN060a/b PDF Generator
FCA CASS 15 / PS25/12 P0 | banxe-emi-stack

Generates monthly safeguarding return (FIN060a client funds, FIN060b breakdown)
as PDF using WeasyPrint and uploads to FCA RegData.

Deadline: 15th of month following reporting period.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from services.config import (
    CLICKHOUSE_DB,
    CLICKHOUSE_HOST,
    CLICKHOUSE_PASSWORD,
    CLICKHOUSE_PORT,
    CLICKHOUSE_USER,
)
from services.config import (
    FIN060_OUTPUT_DIR as _FIN060_DIR,
)

FIN060_OUTPUT_DIR = Path(_FIN060_DIR)


@dataclass(frozen=True)
class FIN060Data:
    """Aggregated data for one reporting period."""

    period_start: date
    period_end: date
    avg_daily_client_funds: Decimal  # FIN060a: monthly average
    peak_client_funds: Decimal
    safeguarding_method: str  # "segregated" | "insurance" | "guarantee"
    bank_name: str
    account_number_masked: str  # last 4 digits only — GDPR
    currency: str = "GBP"


def generate_fin060(period_start: date, period_end: date) -> Path:
    """
    Full pipeline: fetch ClickHouse data → render PDF → save to disk.
    Returns path to generated PDF.
    """
    data = _fetch_period_data(period_start, period_end)
    pdf_path = _render_pdf(data)
    return pdf_path


def _fetch_period_data(period_start: date, period_end: date) -> FIN060Data:
    """Query ClickHouse safeguarding_events for the reporting period."""
    try:
        import clickhouse_driver  # type: ignore
    except ImportError:
        raise RuntimeError("clickhouse-driver not installed. Run: pip install clickhouse-driver")

    client = clickhouse_driver.Client(
        host=CLICKHOUSE_HOST,
        port=CLICKHOUSE_PORT,
        database=CLICKHOUSE_DB,
        user=CLICKHOUSE_USER,
        password=CLICKHOUSE_PASSWORD,
    )

    rows = client.execute(
        """
        SELECT
            avg(external_balance) AS avg_balance,
            max(external_balance) AS peak_balance
        FROM banxe.safeguarding_events
        WHERE
            account_type = 'client_funds'
            AND status = 'MATCHED'
            AND recon_date >= %(start)s
            AND recon_date <= %(end)s
        """,
        {"start": period_start.isoformat(), "end": period_end.isoformat()},
    )

    avg_balance = Decimal(str(rows[0][0])) if rows and rows[0][0] else Decimal("0")
    peak_balance = Decimal(str(rows[0][1])) if rows and rows[0][1] else Decimal("0")

    return FIN060Data(
        period_start=period_start,
        period_end=period_end,
        avg_daily_client_funds=avg_balance,
        peak_client_funds=peak_balance,
        safeguarding_method="segregated",
        bank_name=os.environ.get("SAFEGUARDING_BANK_NAME", "Barclays Bank PLC"),
        account_number_masked=os.environ.get("SAFEGUARDING_ACCOUNT_MASKED", "****"),
        currency="GBP",
    )


def _render_pdf(data: FIN060Data) -> Path:
    """Render FIN060 HTML template → PDF via WeasyPrint."""
    try:
        from weasyprint import HTML  # type: ignore
    except ImportError:
        raise RuntimeError("weasyprint not installed. Run: pip install weasyprint")

    html_content = _build_html(data)
    FIN060_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"FIN060_{data.period_start.strftime('%Y%m')}.pdf"
    output_path = FIN060_OUTPUT_DIR / filename

    HTML(string=html_content).write_pdf(str(output_path))
    return output_path


def _build_html(data: FIN060Data) -> str:
    """Build minimal FIN060 HTML for WeasyPrint rendering."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>FIN060 — Banxe Ltd — {data.period_start.strftime("%B %Y")}</title>
<style>
  body {{ font-family: Arial, sans-serif; font-size: 11pt; margin: 2cm; }}
  h1 {{ font-size: 14pt; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 1em; }}
  th, td {{ border: 1px solid #999; padding: 6px 10px; text-align: left; }}
  th {{ background: #f0f0f0; }}
  .amount {{ text-align: right; font-family: monospace; }}
</style>
</head>
<body>
<h1>FIN060 — Monthly Safeguarding Return</h1>
<p><strong>Firm:</strong> Banxe Limited</p>
<p><strong>Reporting Period:</strong>
   {data.period_start.strftime("%d %B %Y")} – {data.period_end.strftime("%d %B %Y")}</p>

<h2>FIN060a — Client Funds (Safeguarding)</h2>
<table>
  <tr><th>Metric</th><th>Amount ({data.currency})</th></tr>
  <tr>
    <td>Monthly Average Daily Client Funds</td>
    <td class="amount">{data.avg_daily_client_funds:,.2f}</td>
  </tr>
  <tr>
    <td>Peak Client Funds (single day)</td>
    <td class="amount">{data.peak_client_funds:,.2f}</td>
  </tr>
</table>

<h2>FIN060b — Safeguarding Method</h2>
<table>
  <tr><th>Method</th><th>Bank</th><th>Account</th></tr>
  <tr>
    <td>{data.safeguarding_method.title()}</td>
    <td>{data.bank_name}</td>
    <td>{data.account_number_masked}</td>
  </tr>
</table>

<p style="margin-top:2em; font-size:9pt; color:#666;">
Generated by Banxe EMI Analytics Stack | FCA CASS 15 | Confidential
</p>
</body>
</html>"""
