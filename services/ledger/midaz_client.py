"""
Midaz CBS — async balance API client
Implements LedgerPort (I-28: never direct HTTP from domain logic)
FCA CASS 7.15 P0 | banxe-emi-stack
"""

from decimal import Decimal
import os

import httpx

from services.ledger.ledger_port import LedgerInfrastructureError

MIDAZ_BASE_URL = os.environ["MIDAZ_BASE_URL"]
MIDAZ_ORG_ID = os.environ["MIDAZ_ORG_ID"]
MIDAZ_LEDGER_ID = os.environ["MIDAZ_LEDGER_ID"]
MIDAZ_TOKEN = os.environ.get("MIDAZ_TOKEN", "")

_HEADERS = {
    "Authorization": f"Bearer {MIDAZ_TOKEN}",
    "Content-Type": "application/json",
}


async def get_balance(account_id: str) -> Decimal | None:
    """
    Fetch GBP available balance for *account_id* from Midaz.

    Returns Decimal amount, or None if the account is not found / no GBP balance
    (reachable backend, definite answer). Raises LedgerInfrastructureError
    (fail-closed) if Midaz is unreachable or returns a 5xx — never a silent
    balance that masks an outage. NEVER returns float — FCA CASS invariant.
    """
    url = (
        f"{MIDAZ_BASE_URL}/v1/organizations/{MIDAZ_ORG_ID}"
        f"/ledgers/{MIDAZ_LEDGER_ID}/accounts/{account_id}/balances"
    )
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=_HEADERS)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code < 500:
            return None  # reachable, definite (e.g. 404 not found)
        raise LedgerInfrastructureError(
            f"Midaz unavailable fetching balance for account={account_id}"
        ) from exc
    except httpx.RequestError as exc:
        raise LedgerInfrastructureError(
            f"Midaz unavailable fetching balance for account={account_id}"
        ) from exc

    # Midaz returns available balance as integer cents in "available" field
    items = data.get("items", [data])
    for item in items:
        if item.get("assetCode") in ("GBP", "gbp"):
            available = item.get("available", 0)
            # Midaz stores minor units (pence) — convert to pounds
            return Decimal(str(available)) / Decimal("100")
    return None


async def list_accounts() -> list[dict]:
    """Return all accounts for the safeguarding ledger.

    Raises LedgerInfrastructureError (fail-closed) if Midaz is unreachable or
    returns a 5xx; a 4xx returns [] (reachable, definite).
    """
    url = f"{MIDAZ_BASE_URL}/v1/organizations/{MIDAZ_ORG_ID}/ledgers/{MIDAZ_LEDGER_ID}/accounts"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=_HEADERS)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code < 500:
            return []
        raise LedgerInfrastructureError("Midaz unavailable listing accounts") from exc
    except httpx.RequestError as exc:
        raise LedgerInfrastructureError("Midaz unavailable listing accounts") from exc
    return data.get("items", [])
