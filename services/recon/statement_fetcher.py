"""
statement_fetcher.py — StatementFetcher
Block D-recon, IL-007 / IL-011
FCA CASS 7.15: external bank statement ingestion.

Phase 1: CSV file drop (STATEMENT_DIR/stmt_YYYYMMDD.csv)
Phase 2 (FA-07, IL-011): adorsys PSD2 gateway → CAMT.053 XML
         statement_poller.py writes camt053_YYYYMMDD_*.xml → STATEMENT_DIR
         bankstatement_parser.py parses XML → StatementBalance
         fetch_phase2() auto-detects CAMT.053 files if CSV not present.
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path


@dataclass(frozen=True)
class StatementBalance:
    """External bank balance for one account on one date."""

    account_id: str  # internal mapping key (Midaz account UUID)
    currency: str  # ISO-4217
    balance: Decimal  # closing balance in major currency unit (e.g. £100.00)
    statement_date: date
    source_file: str  # filename for audit trail


class StatementFetcher:
    """
    Reads external bank statement CSV and returns per-account balances.

    CSV format (one row per account per date):
        account_id, currency, balance, statement_date, source_file
        019d6332-f274-709a-b3a7-983bc8745886,GBP,5000.00,2026-04-06,stmt_20260406.csv

    In production: replace with SFTP download + CAMT.053 / OFX parser.
    """

    def __init__(self, statement_dir: str | None = None) -> None:
        self._dir = Path(statement_dir or os.environ.get("STATEMENT_DIR", "/data/banxe/statements"))

    def fetch_phase2(self, recon_date: date) -> list[StatementBalance]:
        """
        Phase 2 (FA-07, IL-011): fetch via adorsys PSD2 → CAMT.053.

        Flow:
          1. statement_poller.poll_statements(recon_date) writes CAMT.053 XML to STATEMENT_DIR
          2. bankstatement_parser.parse_camt053() converts XML → StatementBalance list
          3. Falls back to CSV (fetch()) if no XML files found

        Triggered automatically by fetch() when CSV is absent and adorsys is healthy.
        """
        from services.recon.bankstatement_parser import parse_camt053
        from services.recon.statement_poller import health_check, poll_statements

        if not health_check():
            return []  # adorsys not available → caller gets PENDING status

        xml_paths = poll_statements(recon_date)
        balances: list[StatementBalance] = []
        for xml_path in xml_paths:
            balances.extend(parse_camt053(xml_path))
        return balances

    def fetch(self, recon_date: date) -> list[StatementBalance]:
        """
        Unified fetch: try CSV first (Phase 1), then adorsys CAMT.053 (Phase 2).
        Returns [] → PENDING if neither source has data.
        """
        # Phase 1: CSV
        csv_balances = self._fetch_csv(recon_date)
        if csv_balances:
            return csv_balances
        # Phase 2: adorsys PSD2
        return self.fetch_phase2(recon_date)

    def _fetch_csv(self, recon_date: date) -> list[StatementBalance]:
        """Original CSV fetch logic (renamed from fetch)."""
        filename = f"stmt_{recon_date.strftime('%Y%m%d')}.csv"
        path = self._dir / filename
        if not path.exists():
            return []
        balances: list[StatementBalance] = []
        with path.open(newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                balances.append(
                    StatementBalance(
                        account_id=row["account_id"].strip(),
                        currency=row["currency"].strip().upper(),
                        balance=Decimal(row["balance"].strip()),
                        statement_date=date.fromisoformat(row["statement_date"].strip()),
                        source_file=filename,
                    )
                )
        return balances

    def fetch_from_file(self, path: Path) -> list[StatementBalance]:
        """Load from explicit file path (for testing / manual reconciliation)."""
        if not path.exists():
            return []
        balances: list[StatementBalance] = []
        with path.open(newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                balances.append(
                    StatementBalance(
                        account_id=row["account_id"].strip(),
                        currency=row["currency"].strip().upper(),
                        balance=Decimal(row["balance"].strip()),
                        statement_date=date.fromisoformat(row["statement_date"].strip()),
                        source_file=str(path.name),
                    )
                )
        return balances
