"""
api/routers/card_issuing.py
IL-CIM-01 | Phase 19

Card Issuing & Management REST API.
Endpoints:
  POST /cards/issue                  — issue new card
  POST /cards/{id}/activate          — activate card
  POST /cards/{id}/pin               — set PIN (hashed, I-12)
  POST /cards/{id}/freeze            — freeze card
  POST /cards/{id}/unfreeze          — unfreeze card
  POST /cards/{id}/block             — block card (HITL L4)
  POST /cards/{id}/limits            — set spend limits
  POST /cards/{id}/authorise         — authorise transaction
  GET  /cards/{id}                   — get card details
  GET  /cards/{id}/transactions      — list card transactions

FCA compliance:
  - Amounts as strings (I-05)
  - PIN never stored plain (I-12)
  - Audit trail on all operations (I-24)
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.card_issuing.card_agent import CardAgent
from services.card_issuing.card_issuer import CardIssuer
from services.card_issuing.card_lifecycle import CardLifecycle
from services.card_issuing.card_transaction_processor import CardTransactionProcessor
from services.card_issuing.fraud_shield import FraudShield
from services.card_issuing.models import (
    InMemoryCardAudit,
    InMemoryCardStore,
    InMemorySpendLimitStore,
    InMemoryTransactionStore,
)
from services.card_issuing.spend_control import SpendControl

router = APIRouter(tags=["card-issuing"])


# ── Pydantic request models ────────────────────────────────────────────────────


class IssueCardRequest(BaseModel):
    entity_id: str
    card_type: str
    network: str
    name_on_card: str
    actor: str


class ActivateCardRequest(BaseModel):
    actor: str


class SetPINRequest(BaseModel):
    pin: str
    actor: str


class FreezeRequest(BaseModel):
    actor: str
    reason: str = ""


class UnfreezeRequest(BaseModel):
    actor: str


class BlockRequest(BaseModel):
    actor: str
    reason: str


class SetLimitsRequest(BaseModel):
    period: str
    amount: str
    currency: str
    blocked_mccs: list[str] = []
    actor: str


class AuthoriseRequest(BaseModel):
    amount: str
    currency: str
    merchant_name: str
    mcc: str
    country: str
    actor: str


# ── Agent factory ──────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _get_agent() -> CardAgent:
    """Build CardAgent wired to InMemory stubs."""
    card_store = InMemoryCardStore()
    limit_store = InMemorySpendLimitStore()
    txn_store = InMemoryTransactionStore()
    audit = InMemoryCardAudit()

    issuer = CardIssuer(card_store, audit)
    lifecycle = CardLifecycle(card_store, audit)
    spend_control = SpendControl(limit_store, txn_store, audit)
    processor = CardTransactionProcessor(card_store, txn_store, spend_control, audit)
    fraud_shield = FraudShield(txn_store, audit)

    return CardAgent(issuer, lifecycle, spend_control, processor, fraud_shield, audit)


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.post("/cards/issue")
async def issue_card(req: IssueCardRequest) -> dict[str, Any]:
    """Issue a new virtual or physical card."""
    agent = _get_agent()
    try:
        return await agent.issue_card(
            entity_id=req.entity_id,
            card_type_str=req.card_type,
            network_str=req.network,
            name_on_card=req.name_on_card,
            actor=req.actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/cards/{card_id}/activate")
async def activate_card(card_id: str, req: ActivateCardRequest) -> dict[str, Any]:
    """Activate a PENDING card."""
    agent = _get_agent()
    try:
        return await agent.activate_card(card_id, req.actor)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/cards/{card_id}/pin")
async def set_pin(card_id: str, req: SetPINRequest) -> dict[str, Any]:
    """Set card PIN (stored as hash, never plain — I-12)."""
    if not (len(req.pin) == 4 and req.pin.isdigit()):
        raise HTTPException(status_code=422, detail="PIN must be exactly 4 digits")
    agent = _get_agent()
    try:
        return await agent.set_pin(card_id, req.pin, req.actor)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/cards/{card_id}/freeze")
async def freeze_card(card_id: str, req: FreezeRequest) -> dict[str, Any]:
    """Freeze an active card."""
    agent = _get_agent()
    try:
        return await agent.freeze_card(card_id, req.actor, req.reason)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/cards/{card_id}/unfreeze")
async def unfreeze_card(card_id: str, req: UnfreezeRequest) -> dict[str, Any]:
    """Unfreeze a frozen card."""
    agent = _get_agent()
    try:
        return await agent.unfreeze_card(card_id, req.actor)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/cards/{card_id}/block")
async def block_card(card_id: str, req: BlockRequest) -> dict[str, Any]:
    """Block a card (HITL L4 gate — irreversible)."""
    agent = _get_agent()
    try:
        return await agent.block_card(card_id, req.actor, req.reason)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/cards/{card_id}/limits")
async def set_limits(card_id: str, req: SetLimitsRequest) -> dict[str, Any]:
    """Set per-card spend limits (period, MCC block, geo-restrictions)."""
    agent = _get_agent()
    try:
        return await agent.set_limits(
            card_id=card_id,
            period_str=req.period,
            amount_str=req.amount,
            currency=req.currency,
            blocked_mccs=req.blocked_mccs,
            actor=req.actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/cards/{card_id}/authorise")
async def authorise_transaction(card_id: str, req: AuthoriseRequest) -> dict[str, Any]:
    """Authorise a card transaction (amount as string, I-05)."""
    agent = _get_agent()
    try:
        return await agent.authorise_transaction(
            card_id=card_id,
            amount_str=req.amount,
            currency=req.currency,
            merchant_name=req.merchant_name,
            mcc=req.mcc,
            country=req.country,
            actor=req.actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/cards/{card_id}")
async def get_card(card_id: str) -> dict[str, Any]:
    """Get card details by ID."""
    agent = _get_agent()
    result = await agent.get_card(card_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Card {card_id} not found")
    return result


@router.get("/cards/{card_id}/transactions")
async def list_transactions(card_id: str) -> list[dict[str, Any]]:
    """List cleared transactions for a card."""
    agent = _get_agent()
    return await agent.list_transactions(card_id)
