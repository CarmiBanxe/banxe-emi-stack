"""
api/routers/midaz_mcp.py — Midaz MCP endpoints
IL-MCP-01 | banxe-emi-stack
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.midaz_mcp.midaz_agent import MidazAgent, MidazHITLProposal
from services.midaz_mcp.midaz_client import BLOCKED_JURISDICTIONS, MidazClient
from services.midaz_mcp.midaz_models import TransactionEntry

logger = logging.getLogger("banxe.midaz_mcp")
router = APIRouter(tags=["MidazMCP"])

_client = MidazClient()
_agent = MidazAgent(_client)


class CreateOrgRequest(BaseModel):
    name: str
    legal_name: str
    country: str = "GB"


class CreateLedgerRequest(BaseModel):
    org_id: str
    name: str


class CreateTransactionRequest(BaseModel):
    ledger_id: str
    entries: list[TransactionEntry]


@router.post("/midaz/organizations", summary="Create Midaz organization (I-02)")
async def create_organization(body: CreateOrgRequest):
    if body.country in BLOCKED_JURISDICTIONS:
        raise HTTPException(status_code=400, detail=f"Country {body.country!r} is blocked (I-02)")
    org = await _client.create_organization(body.name, body.legal_name, body.country)
    return {"org_id": org.org_id, "name": org.name, "country": org.country}


@router.post("/midaz/ledgers", summary="Create Midaz ledger")
async def create_ledger(body: CreateLedgerRequest):
    ledger = await _client.create_ledger(body.org_id, body.name)
    return {"ledger_id": ledger.ledger_id, "org_id": ledger.org_id, "name": ledger.name}


@router.post(
    "/midaz/transactions",
    summary="Create transaction (I-27 HITL L4 for amounts >= £10k)",
)
async def create_transaction(body: CreateTransactionRequest):
    result = await _agent.submit_transaction(body.ledger_id, body.entries)
    if isinstance(result, MidazHITLProposal):
        return {
            "status": "HITL_REQUIRED",
            "proposal_id": result.proposal_id,
            "reason": result.reason,
            "requires_approval_from": result.requires_approval_from,
        }
    return {"transaction_id": result.transaction_id, "status": result.status}


@router.get("/midaz/balances/{account_id}", summary="Get account balances")
async def get_balances(account_id: str):
    balances = await _client.get_balances(account_id)
    return {
        "account_id": account_id,
        "balances": [{"asset_code": b.asset_code, "amount": b.amount} for b in balances],
    }


@router.get("/midaz/accounts/{ledger_id}", summary="List ledger accounts")
async def list_accounts(ledger_id: str):
    accounts = await _client.list_accounts(ledger_id)
    return {
        "ledger_id": ledger_id,
        "accounts": [{"account_id": a.account_id, "name": a.name} for a in accounts],
    }
