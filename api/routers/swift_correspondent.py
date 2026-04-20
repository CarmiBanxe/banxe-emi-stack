"""
api/routers/swift_correspondent.py
SWIFT & Correspondent Banking REST API
IL-SWF-01 | Sprint 34 | Phase 47

FCA: PSR 2017, SWIFT gpi SRD, MLR 2017 Reg.28, FCA SUP 15.8
Trust Zone: RED

10 endpoints at /v1/swift/*
HITL L4 for all send/hold/cancel operations (I-11, I-27).
"""

from __future__ import annotations

from decimal import Decimal
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.swift_correspondent.charges_calculator import ChargesCalculator
from services.swift_correspondent.correspondent_registry import CorrespondentRegistry
from services.swift_correspondent.gpi_tracker import SWIFTGPITracker
from services.swift_correspondent.message_builder import SWIFTMessageBuilder
from services.swift_correspondent.models import (
    ChargeCode,
    CorrespondentType,
    InMemoryCorrespondentStore,
    InMemoryMessageStore,
    InMemoryNostroStore,
)
from services.swift_correspondent.nostro_reconciler import NostroReconciler
from services.swift_correspondent.swift_agent import SWIFTAgent

logger = logging.getLogger(__name__)

router = APIRouter(tags=["SWIFT & Correspondent Banking"])

# ── Module-level singletons ───────────────────────────────────────────────

_message_store = InMemoryMessageStore()
_correspondent_store = InMemoryCorrespondentStore()
_nostro_store = InMemoryNostroStore()

_builder = SWIFTMessageBuilder(store=_message_store)
_registry = CorrespondentRegistry(store=_correspondent_store)
_reconciler = NostroReconciler(store=_nostro_store)
_gpi_tracker = SWIFTGPITracker(store=_message_store)
_charges_calc = ChargesCalculator()
_agent = SWIFTAgent(builder=_builder)


# ── Request / Response models ─────────────────────────────────────────────


class MT103Request(BaseModel):
    """Request model for MT103 Customer Credit Transfer."""

    sender_bic: str
    receiver_bic: str
    amount: str  # Decimal string (I-22)
    currency: str
    ordering_customer: str
    beneficiary_customer: str
    remittance_info: str
    charge_code: str = "SHA"


class MT202Request(BaseModel):
    """Request model for MT202 Financial Institution Transfer."""

    sender_bic: str
    receiver_bic: str
    amount: str  # Decimal string (I-22)
    currency: str
    ordering_institution: str
    beneficiary_institution: str


class HoldRequest(BaseModel):
    """Request to hold a SWIFT message."""

    reason: str
    actor: str = "API"


class CancelRequest(BaseModel):
    """Request to cancel a SWIFT message."""

    reason: str
    actor: str = "API"


class RegisterCorrespondentRequest(BaseModel):
    """Request to register a correspondent bank."""

    bic: str
    bank_name: str
    country_code: str
    correspondent_type: str = "nostro"
    currencies: list[str]
    nostro_account: str | None = None
    vostro_account: str | None = None


class NostroReconcileRequest(BaseModel):
    """Request for nostro reconciliation snapshot."""

    our_balance: str  # Decimal string (I-22)
    their_balance: str  # Decimal string (I-22)


# ── Endpoints ─────────────────────────────────────────────────────────────


@router.post("/messages/mt103")
async def build_mt103(req: MT103Request) -> dict[str, object]:
    """Build SWIFT MT103 Customer Credit Transfer.

    FATF greylist check on receiver country (I-03).
    BIC validated (8 or 11 chars).
    Remittance field 70 capped at 140 chars.
    """
    try:
        charge_code = ChargeCode(req.charge_code.upper())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid charge_code: {req.charge_code}")

    try:
        msg = _builder.build_mt103(
            sender_bic=req.sender_bic,
            receiver_bic=req.receiver_bic,
            amount=Decimal(req.amount),
            currency=req.currency,
            ordering_customer=req.ordering_customer,
            beneficiary_customer=req.beneficiary_customer,
            remittance_info=req.remittance_info,
            charge_code=charge_code,
        )
    except (ValueError, Exception) as e:
        raise HTTPException(status_code=400, detail=str(e))

    return msg.model_dump()


@router.post("/messages/mt202")
async def build_mt202(req: MT202Request) -> dict[str, object]:
    """Build SWIFT MT202 Financial Institution Transfer.

    SHA-256 message_id. BIC validated. Amount as Decimal (I-22).
    """
    try:
        msg = _builder.build_mt202(
            sender_bic=req.sender_bic,
            receiver_bic=req.receiver_bic,
            amount=Decimal(req.amount),
            currency=req.currency,
            ordering_institution=req.ordering_institution,
            beneficiary_institution=req.beneficiary_institution,
        )
    except (ValueError, Exception) as e:
        raise HTTPException(status_code=400, detail=str(e))

    return msg.model_dump()


@router.get("/messages/{message_id}")
async def get_message(message_id: str) -> dict[str, object]:
    """Get a SWIFT message by ID."""
    msg = _builder.get_message(message_id)
    if msg is None:
        raise HTTPException(status_code=404, detail=f"Message {message_id} not found")
    return msg.model_dump()


@router.post("/messages/{message_id}/send")
async def send_message(message_id: str) -> dict[str, object]:
    """Propose SWIFT message send — returns HITLProposal (L4, TREASURY_OPS, I-27).

    SEND is irreversible. Always requires human approval.
    """
    from dataclasses import asdict

    proposal = _agent.process_send(message_id)
    return asdict(proposal)


@router.post("/messages/{message_id}/hold")
async def hold_message(message_id: str, req: HoldRequest) -> dict[str, object]:
    """Propose SWIFT message hold — returns HITLProposal (L4, I-27)."""
    from dataclasses import asdict

    proposal = _agent.process_hold(message_id, req.reason)
    return asdict(proposal)


@router.post("/messages/{message_id}/cancel")
async def cancel_message(message_id: str, req: CancelRequest) -> dict[str, object]:
    """Propose SWIFT message cancellation — returns HITLProposal (L4, I-27).

    Cancellation is irreversible. Always requires human approval.
    """
    from dataclasses import asdict

    proposal = _builder.cancel_message(message_id, req.reason, req.actor)
    return asdict(proposal)


@router.get("/correspondents")
async def list_correspondents(currency: str = "") -> dict[str, object]:
    """List correspondent banks, optionally filtered by currency.

    FATF risk status included in response (I-03).
    """
    if currency:
        banks = _registry.lookup_by_currency(currency.upper())
    else:
        summary = _registry.get_registry_summary()
        banks_by_currency: list[object] = []
        seen: set[str] = set()
        for cur in ["GBP", "EUR", "USD", "JPY", "CHF"]:
            for bank in _registry.lookup_by_currency(cur):
                if bank.bank_id not in seen:
                    banks_by_currency.append(bank.model_dump())
                    seen.add(bank.bank_id)
        return {"correspondents": banks_by_currency, "summary": summary}

    return {"correspondents": [b.model_dump() for b in banks], "count": len(banks)}


@router.post("/correspondents")
async def register_correspondent(req: RegisterCorrespondentRequest) -> dict[str, object]:
    """Register a correspondent bank.

    FATF greylist check on country (I-03). Blocked jurisdictions rejected (I-02).
    """
    try:
        corr_type = CorrespondentType(req.correspondent_type.lower())
    except ValueError:
        raise HTTPException(
            status_code=400, detail=f"Invalid correspondent_type: {req.correspondent_type}"
        )

    try:
        bank = _registry.register_correspondent(
            bic=req.bic,
            bank_name=req.bank_name,
            country_code=req.country_code,
            correspondent_type=corr_type,
            currencies=req.currencies,
            nostro_account=req.nostro_account,
            vostro_account=req.vostro_account,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return bank.model_dump()


@router.get("/nostro/{bank_id}/{currency}")
async def get_nostro_position(bank_id: str, currency: str) -> dict[str, object]:
    """Get latest nostro position for a bank/currency pair.

    Returns mismatch amount and reconciliation status.
    """
    has_mismatch, mismatch_amount = _reconciler.check_mismatch(bank_id, currency.upper())
    latest = _nostro_store.get_latest(bank_id, currency.upper())

    if latest is None:
        return {
            "bank_id": bank_id,
            "currency": currency.upper(),
            "has_position": False,
            "has_mismatch": False,
            "mismatch_amount": "0",
        }

    return {
        **latest.model_dump(),
        "has_mismatch": has_mismatch,
        "mismatch_amount": str(mismatch_amount),
    }


@router.get("/gpi/{uetr}")
async def get_gpi_status(uetr: str) -> dict[str, object]:
    """Get SWIFT gpi status for a UETR.

    Returns ACSP/ACCC/RJCT status per SWIFT gpi SRD.
    """
    status = _gpi_tracker.get_gpi_status(uetr)
    return status.model_dump()
