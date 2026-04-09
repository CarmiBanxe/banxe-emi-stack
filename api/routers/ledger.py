"""
api/routers/ledger.py — Ledger account and balance endpoints
IL-046 | banxe-emi-stack

GET /v1/ledger/accounts              — list ledger accounts
GET /v1/ledger/accounts/{id}/balance — get account balance

In sandbox: returns mock data (Midaz env vars not required).
In production: proxies to Midaz CBS via services/ledger/midaz_client.py.
FCA CASS 7.15: balances must be fetched in real-time, never cached >60s.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException

from api.models.ledger import (
    AccountBalanceResponse,
    AccountListResponse,
    AccountResponse,
)

router = APIRouter(tags=["Ledger"])

# ── Sandbox mock data (used when MIDAZ_BASE_URL is not set) ──────────────────
_MOCK_ACCOUNTS = [
    {
        "account_id": "acc-operational-001",
        "name": "Operational Account (GBP)",
        "type": "OPERATIONAL",
        "currency": "GBP",
        "status": "ACTIVE",
    },
    {
        "account_id": "acc-client-funds-001",
        "name": "Client Funds Account (GBP)",
        "type": "SAFEGUARDING",
        "currency": "GBP",
        "status": "ACTIVE",
    },
]

_MOCK_BALANCES: dict[str, dict] = {
    "acc-operational-001": {
        "available": "4700.00",
        "total": "4750.00",
        "on_hold": "50.00",
        "currency": "GBP",
    },
    "acc-client-funds-001": {
        "available": "125000.00",
        "total": "125000.00",
        "on_hold": "0.00",
        "currency": "GBP",
    },
}


def _is_sandbox() -> bool:
    return not os.environ.get("MIDAZ_BASE_URL")


@router.get(
    "/ledger/accounts",
    response_model=AccountListResponse,
    summary="List ledger accounts",
)
async def list_accounts() -> AccountListResponse:
    """
    Returns all ledger accounts for the organisation.
    In production: fetches from Midaz CBS.
    FCA CASS 15: safeguarding accounts must be identifiable.
    """
    if _is_sandbox():
        accounts = [AccountResponse(**a) for a in _MOCK_ACCOUNTS]
        return AccountListResponse(accounts=accounts, total=len(accounts))

    from services.ledger import midaz_client  # pragma: no cover

    raw = await midaz_client.list_accounts()  # pragma: no cover
    accounts = [  # pragma: no cover
        AccountResponse(
            account_id=a.get("id", ""),
            name=a.get("name", ""),
            type=a.get("type", ""),
            currency=a.get("assetCode", "GBP"),
            status=a.get("status", "ACTIVE"),
        )
        for a in raw
    ]
    return AccountListResponse(  # pragma: no cover
        accounts=accounts, total=len(accounts)
    )


@router.get(
    "/ledger/accounts/{account_id}/balance",
    response_model=AccountBalanceResponse,
    summary="Get account balance",
)
async def get_balance(account_id: str) -> AccountBalanceResponse:
    """
    Returns real-time balance for the specified account.
    FCA CASS 7.15.17R: balance data must be current (not stale).
    Amounts returned as decimal strings (I-05, never float).
    """
    if _is_sandbox():
        data = _MOCK_BALANCES.get(account_id)
        if data is None:
            raise HTTPException(
                status_code=404,
                detail=f"Account {account_id} not found",
            )
        return AccountBalanceResponse(
            account_id=account_id,
            available=data["available"],
            total=data["total"],
            on_hold=data.get("on_hold"),
            currency=data["currency"],
        )

    from services.ledger import midaz_client  # pragma: no cover

    balance = await midaz_client.get_balance(account_id)  # pragma: no cover
    if balance is None:  # pragma: no cover
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")
    return AccountBalanceResponse(  # pragma: no cover
        account_id=account_id,
        available=str(balance),
        total=str(balance),
        currency="GBP",
    )
