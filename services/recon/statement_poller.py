"""
statement_poller.py — adorsys PSD2 daily statement poller
FA-07 | IL-011 | FCA CASS 7.15 | banxe-emi-stack

Polls adorsys open-banking-gateway for CAMT.053 account statements,
writes XML files to STATEMENT_DIR for bankstatement_parser.py to consume.

Phase 0: sandbox (aspsp-mock) — no real bank credentials needed.
Phase 1: real bank (Barclays/HSBC PSD2) — requires AISP registration + eIDAS cert.
"""
from __future__ import annotations

import logging
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

ADORSYS_PSD2_URL = os.environ.get("ADORSYS_PSD2_URL", "http://localhost:8888")
ADORSYS_BANK_IBAN = os.environ.get("ADORSYS_BANK_IBAN", "")
STATEMENT_DIR = Path(os.environ.get("STATEMENT_DIR", "/data/banxe/statements"))

# Safeguarding account IBANs (set in .env — not hardcoded)
OPERATIONAL_IBAN = os.environ.get("SAFEGUARDING_OPERATIONAL_IBAN", "")
CLIENT_FUNDS_IBAN = os.environ.get("SAFEGUARDING_CLIENT_FUNDS_IBAN", "")


def poll_statements(recon_date: Optional[date] = None) -> list[Path]:
    """
    Fetch CAMT.053 statements for all safeguarding accounts from adorsys gateway.

    Returns list of paths to written CAMT.053 XML files.
    Files are named: camt053_YYYYMMDD_<last4iban>.xml
    """
    if recon_date is None:
        recon_date = date.today() - timedelta(days=1)  # yesterday's statement

    ibans = [iban for iban in [OPERATIONAL_IBAN, CLIENT_FUNDS_IBAN] if iban]

    if not ibans:
        logger.warning(
            "No IBANs configured. Set SAFEGUARDING_OPERATIONAL_IBAN and "
            "SAFEGUARDING_CLIENT_FUNDS_IBAN in .env"
        )
        return []

    STATEMENT_DIR.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for iban in ibans:
        path = _fetch_camt053(iban, recon_date)
        if path:
            written.append(path)

    return written


def _fetch_camt053(iban: str, recon_date: date) -> Optional[Path]:
    """
    Call adorsys open-banking-gateway AIS endpoint and retrieve CAMT.053.

    Endpoint: GET /v1/accounts/{account-id}/transactions
    Accept:   application/xml (CAMT.053)
    """
    date_str = recon_date.strftime("%Y-%m-%d")
    last4 = iban[-4:] if len(iban) >= 4 else iban

    try:
        # Step 1: resolve account-id from IBAN
        account_id = _resolve_account_id(iban)
        if not account_id:
            logger.warning("Could not resolve account-id for IBAN %s", iban)
            return None

        # Step 2: fetch transactions as CAMT.053 XML
        url = f"{ADORSYS_PSD2_URL}/v1/accounts/{account_id}/transactions"
        params = {
            "dateFrom": date_str,
            "dateTo": date_str,
            "bookingStatus": "booked",
        }
        headers = {
            "Accept": "application/xml",
            "X-Request-ID": f"banxe-recon-{date_str}-{last4}",
        }

        resp = httpx.get(url, params=params, headers=headers, timeout=30.0)
        resp.raise_for_status()

        # Step 3: write to STATEMENT_DIR
        filename = f"camt053_{recon_date.strftime('%Y%m%d')}_{last4}.xml"
        outpath = STATEMENT_DIR / filename
        outpath.write_bytes(resp.content)

        logger.info("CAMT.053 written: %s (%d bytes)", outpath, len(resp.content))
        return outpath

    except httpx.HTTPStatusError as exc:
        logger.error(
            "adorsys gateway HTTP %s for IBAN %s: %s",
            exc.response.status_code, iban, exc.response.text[:200],
        )
    except httpx.RequestError as exc:
        logger.error("adorsys gateway connection error for IBAN %s: %s", iban, exc)

    return None


def _resolve_account_id(iban: str) -> Optional[str]:
    """
    GET /v1/accounts → find account-id matching IBAN.
    Returns the adorsys internal account UUID.
    """
    try:
        resp = httpx.get(
            f"{ADORSYS_PSD2_URL}/v1/accounts",
            headers={"Accept": "application/json"},
            timeout=10.0,
        )
        resp.raise_for_status()
        accounts = resp.json().get("accounts", [])
        for acct in accounts:
            if acct.get("iban") == iban:
                return acct.get("resourceId") or acct.get("id")
    except Exception as exc:
        logger.error("Failed to list accounts from adorsys: %s", exc)
    return None


def health_check() -> bool:
    """Return True if adorsys gateway is reachable."""
    try:
        resp = httpx.get(
            f"{ADORSYS_PSD2_URL}/actuator/health", timeout=5.0
        )
        return resp.status_code == 200
    except Exception:
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ok = health_check()
    print(f"adorsys gateway health: {'OK' if ok else 'UNREACHABLE'}")
    if ok:
        paths = poll_statements()
        print(f"Statements written: {[str(p) for p in paths]}")
