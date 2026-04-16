"""
api/routers/merchant_acquiring.py
IL-MAG-01 | Phase 20

Merchant Acquiring Gateway REST API.
Endpoints:
  POST /v1/merchants/onboard                  → onboard_merchant
  POST /v1/merchants/{id}/approve-kyb         → approve_kyb
  GET  /v1/merchants/{id}                     → get_merchant
  GET  /v1/merchants                          → list_merchants
  POST /v1/merchants/{id}/payments            → accept_payment
  POST /v1/merchants/payments/{payment_id}/3ds → complete_3ds
  GET  /v1/merchants/{id}/settlements         → list_settlements
  POST /v1/merchants/{id}/settlements         → create_settlement
  POST /v1/merchants/{id}/chargebacks         → receive_chargeback
  GET  /v1/merchants/{id}/risk-score          → score_merchant

FCA compliance:
  - Amounts always as strings (I-05, never float)
  - KYB required before payment acceptance
  - HITL required for suspend/terminate (I-27)
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.merchant_acquiring.chargeback_handler import ChargebackHandler
from services.merchant_acquiring.merchant_agent import MerchantAgent
from services.merchant_acquiring.merchant_onboarding import MerchantOnboarding
from services.merchant_acquiring.merchant_risk_scorer import MerchantRiskScorer
from services.merchant_acquiring.models import (
    InMemoryDisputeStore,
    InMemoryMAAudit,
    InMemoryMerchantStore,
    InMemoryPaymentStore,
    InMemorySettlementStore,
)
from services.merchant_acquiring.payment_gateway import PaymentGateway
from services.merchant_acquiring.settlement_engine import SettlementEngine

router = APIRouter(tags=["merchant-acquiring"])


# ── Pydantic request models ────────────────────────────────────────────────────


class OnboardRequest(BaseModel):
    name: str
    legal_name: str
    mcc: str
    country: str
    website: str | None = None
    daily_limit: str
    monthly_limit: str
    actor: str


class AcceptPaymentRequest(BaseModel):
    amount: str
    currency: str
    card_last_four: str
    reference: str
    actor: str


class ReceiveChargebackRequest(BaseModel):
    payment_id: str
    amount: str
    currency: str
    reason: str
    actor: str


# ── Agent factory ──────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _get_agent() -> MerchantAgent:
    """Build MerchantAgent wired to InMemory stubs."""
    merchant_store = InMemoryMerchantStore()
    payment_store = InMemoryPaymentStore()
    settlement_store = InMemorySettlementStore()
    dispute_store = InMemoryDisputeStore()
    audit = InMemoryMAAudit()

    onboarding = MerchantOnboarding(merchant_store, audit)
    gateway = PaymentGateway(merchant_store, payment_store, audit)
    settlement = SettlementEngine(payment_store, settlement_store, audit)
    chargeback = ChargebackHandler(dispute_store, audit)
    risk_scorer = MerchantRiskScorer(merchant_store, payment_store, dispute_store, audit)

    return MerchantAgent(onboarding, gateway, settlement, chargeback, risk_scorer, audit)


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/merchants/onboard", summary="Onboard a new merchant (KYB)")
async def onboard_merchant(body: OnboardRequest) -> dict[str, Any]:
    try:
        return await _get_agent().onboard_merchant(
            body.name,
            body.legal_name,
            body.mcc,
            body.country,
            body.website,
            body.daily_limit,
            body.monthly_limit,
            body.actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/merchants/{merchant_id}/approve-kyb",
    summary="Approve KYB for a merchant",
)
async def approve_kyb(merchant_id: str, actor: str = "system") -> dict[str, Any]:
    try:
        return await _get_agent().approve_kyb(merchant_id, actor)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/merchants/{merchant_id}", summary="Get merchant by ID")
async def get_merchant(merchant_id: str) -> dict[str, Any]:
    result = await _get_agent().get_merchant(merchant_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Merchant {merchant_id!r} not found")
    return result


@router.get("/merchants", summary="List all merchants")
async def list_merchants() -> list[dict[str, Any]]:
    return await _get_agent().list_merchants()


@router.post("/merchants/{merchant_id}/payments", summary="Accept a card payment")
async def accept_payment(merchant_id: str, body: AcceptPaymentRequest) -> dict[str, Any]:
    try:
        return await _get_agent().accept_payment(
            merchant_id,
            body.amount,
            body.currency,
            body.card_last_four,
            body.reference,
            body.actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/merchants/payments/{payment_id}/3ds",
    summary="Complete 3DS2 challenge",
)
async def complete_3ds(payment_id: str, actor: str = "system") -> dict[str, Any]:
    try:
        return await _get_agent().complete_3ds(payment_id, actor)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/merchants/{merchant_id}/settlements", summary="List settlements")
async def list_settlements(merchant_id: str) -> list[dict[str, Any]]:
    return await _get_agent().list_settlements(merchant_id)


@router.post("/merchants/{merchant_id}/settlements", summary="Create settlement batch")
async def create_settlement(merchant_id: str, actor: str = "system") -> dict[str, Any]:
    try:
        return await _get_agent().create_settlement(merchant_id, actor)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/merchants/{merchant_id}/chargebacks", summary="Receive a chargeback")
async def receive_chargeback(merchant_id: str, body: ReceiveChargebackRequest) -> dict[str, Any]:
    try:
        return await _get_agent().receive_chargeback(
            merchant_id,
            body.payment_id,
            body.amount,
            body.currency,
            body.reason,
            body.actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/merchants/{merchant_id}/risk-score", summary="Get merchant risk score")
async def score_merchant(merchant_id: str) -> dict[str, Any]:
    try:
        return await _get_agent().score_merchant(merchant_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
