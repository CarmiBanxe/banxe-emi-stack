"""
Midaz CBS — async balance API client
Implements LedgerPort (I-28: never direct HTTP from domain logic)
FCA CASS 7.15 P0 | banxe-emi-stack
"""
import os
from decimal import Decimal
from typing import Optional
import httpx

MIDAZ_BASE_URL = os.environ["MIDAZ_BASE_URL"]
MIDAZ_ORG_ID = os.environ["MIDAZ_ORG_ID"]
MIDAZ_LEDGER_ID = os.environ["MIDAZ_LEDGER_ID"]
MIDAZ_TOKEN = os.environ.get("MIDAZ_TOKEN", "")

_HEADERS = {
    "Authorization": f"Bearer {MIDAZ_TOKEN}",
    "Content-Type": "application/json",
}


async def get_balance(account_id: str) -> Optional[Decimal]:
    """
    Fetch GBP available balance for *account_id* from Midaz.

    Returns Decimal amount or None if the account is not found.
    NEVER returns float — FCA CASS invariant.
    """
    url = (
        f"{MIDAZ_BASE_URL}/v1/organizations/{MIDAZ_ORG_ID}"
        f"/ledgers/{MIDAZ_LEDGER_ID}/accounts/{account_id}/balances"
    )
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = client.get(url, headers=_HEADERS)  # type: ignore[attr-defined]
        resp = await client.get(url, headers=_HEADERS)
        resp.raise_for_status()
        data = resp.json()

    # Midaz returns available balance as integer cents in "available" field
    items = data.get("items", [data])
    for item in items:
        if item.get("assetCode") in ("GBP", "gbp"):
            available = item.get("available", 0)
            # Midaz stores minor units (pence) — convert to pounds
            return Decimal(str(available)) / Decimal("100")
    return None


async def list_accounts() -> list[dict]:
    """Return all accounts for the safeguarding ledger."""
    url = (
        f"{MIDAZ_BASE_URL}/v1/organizations/{MIDAZ_ORG_ID}"
        f"/ledgers/{MIDAZ_LEDGER_ID}/accounts"
    )
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, headers=_HEADERS)
        resp.raise_for_status()
    return resp.json().get("items", [])
