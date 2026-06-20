"""api/routers/account_sot.py — Advisory account/balance SoT endpoints (MIG-M2.2) | banxe-emi-stack.

GET /v1/account-sot/metadata          — advisory account metadata (balance-free)
GET /v1/account-sot/virtual-accounts  — virtual-account descriptors (balance-free)
GET /v1/account-sot/intermediaries    — intermediary-bank descriptors (reference-only)

Advisory account-metadata SoT (MIG-M2.2). Balance-free; does NOT call the Midaz LedgerPort (live
balances stay in /v1/ledger/*, ADR-013). Payments = future projection-consumer (MIG-M1.3). Sandbox:
config-as-data mock. Consumes the accounts-connector contract baseline (MIG-M2.0/M2.7) at the proto
level. No live mutation (operator-gated, ADR-103 PART 2).
"""

from __future__ import annotations

from fastapi import APIRouter

from api.models.account_sot import (
    AccountSoTMetadataResponse,
    IntermediaryListResponse,
    VirtualAccountListResponse,
    account_sot_metadata_response,
    intermediary_list_response,
    virtual_account_list_response,
)

router = APIRouter(prefix="/account-sot", tags=["account-sot"])


@router.get("/metadata", response_model=AccountSoTMetadataResponse)
async def get_account_metadata() -> AccountSoTMetadataResponse:
    return account_sot_metadata_response()


@router.get("/virtual-accounts", response_model=VirtualAccountListResponse)
async def get_virtual_accounts() -> VirtualAccountListResponse:
    return virtual_account_list_response()


@router.get("/intermediaries", response_model=IntermediaryListResponse)
async def get_intermediaries() -> IntermediaryListResponse:
    return intermediary_list_response()
