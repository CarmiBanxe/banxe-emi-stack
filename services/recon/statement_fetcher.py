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
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import logging
import os
from pathlib import Path
import time

logger = logging.getLogger(__name__)

# Phase 2: OAuth2 ASPSP config (read from env — never hardcoded)
ASPSP_BASE_URL = os.environ.get("ASPSP_BASE_URL", "")
ASPSP_CLIENT_ID = os.environ.get("ASPSP_CLIENT_ID", "")
ASPSP_CLIENT_SECRET = os.environ.get("ASPSP_CLIENT_SECRET", "")
ASPSP_CERT_PATH = os.environ.get("ASPSP_CERT_PATH", "")


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

    def fetch_with_oauth(self, recon_date: date, access_token: str) -> list[StatementBalance]:
        """
        Phase 2 (FA-07): Fetch bank statement from real ASPSP API using OAuth2 token.

        Retry logic: 3 attempts with exponential backoff (1s, 2s, 4s).
        Reads ASPSP_BASE_URL, ASPSP_CLIENT_ID, ASPSP_CLIENT_SECRET, ASPSP_CERT_PATH from env.
        Falls back to [] on exhausted retries — caller will fall back to CSV or PENDING.
        """
        import httpx

        # Read env at call time so tests can monkeypatch os.environ at runtime
        aspsp_base_url = os.environ.get("ASPSP_BASE_URL", "")
        aspsp_cert_path = os.environ.get("ASPSP_CERT_PATH", "")

        if not aspsp_base_url:
            logger.warning("ASPSP_BASE_URL not set — fetch_with_oauth skipped")
            return []

        date_str = recon_date.strftime("%Y-%m-%d")
        url = f"{aspsp_base_url}/v1/accounts/statements"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "X-Request-ID": f"banxe-recon-oauth-{date_str}",
        }
        params = {"dateFrom": date_str, "dateTo": date_str}

        cert = aspsp_cert_path if aspsp_cert_path else None
        delays = [1, 2, 4]  # exponential backoff seconds

        for attempt, delay in enumerate(delays, start=1):
            try:
                with httpx.Client(cert=cert, timeout=30.0) as client:
                    resp = client.get(url, headers=headers, params=params)
                    resp.raise_for_status()
                    data = resp.json()
                    return self._parse_aspsp_json(data, recon_date)
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                logger.warning(
                    "fetch_with_oauth attempt %d/%d HTTP %s for %s",
                    attempt,
                    len(delays),
                    status,
                    date_str,
                )
                if status not in (429, 500, 502, 503, 504):
                    break  # non-retryable error
            except httpx.RequestError as exc:
                logger.warning(
                    "fetch_with_oauth attempt %d/%d connection error: %s",
                    attempt,
                    len(delays),
                    exc,
                )

            if attempt < len(delays):
                time.sleep(delay)

        logger.error(
            "fetch_with_oauth exhausted %d retries for %s — returning []", len(delays), date_str
        )
        return []

    def _parse_aspsp_json(self, data: dict, recon_date: date) -> list[StatementBalance]:
        """Parse ASPSP JSON response into StatementBalance list."""
        balances: list[StatementBalance] = []
        accounts = data.get("accounts", []) or data.get("statements", [])
        for acct in accounts:
            account_id = acct.get("account_id") or acct.get("resourceId", "")
            currency = acct.get("currency", "GBP")
            balance_raw = acct.get("closing_balance") or acct.get("balance", "0")
            try:
                balance = Decimal(str(balance_raw))
            except Exception:
                logger.error("Invalid balance value '%s' for account %s", balance_raw, account_id)
                continue
            if account_id:
                balances.append(
                    StatementBalance(
                        account_id=account_id,
                        currency=currency,
                        balance=balance,
                        statement_date=recon_date,
                        source_file=f"aspsp_oauth_{recon_date.strftime('%Y%m%d')}.json",
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
