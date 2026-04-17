"""
api/routers/loyalty.py — Loyalty & Rewards REST API
IL-LRE-01 | Phase 29 | banxe-emi-stack

Endpoints (prefix /v1/loyalty embedded):
  GET  /v1/loyalty/balance/{customer_id}              — get points balance + tier
  POST /v1/loyalty/earn                               — earn points from spend
  POST /v1/loyalty/bonus                              — apply bonus (HITL >10k, I-27)
  GET  /v1/loyalty/history/{customer_id}              — earn/spend history
  POST /v1/loyalty/redeem                             — redeem points for reward
  GET  /v1/loyalty/options/{customer_id}              — list redemption options
  GET  /v1/loyalty/tier/{customer_id}/evaluate        — evaluate and apply tier change
  GET  /v1/loyalty/tiers                              — list all tiers
  POST /v1/loyalty/cashback                           — process MCC-based cashback
  GET  /v1/loyalty/expiry/{customer_id}               — expiry forecast

FCA: PS22/9 (Consumer Duty — fair value), BCOBS 5 (post-sale engagement)
Invariants: I-01 (Decimal points), I-05 (amounts as strings), I-27 (HITL bonus >10k)
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.loyalty.loyalty_agent import LoyaltyAgent

router = APIRouter(tags=["loyalty"])


@lru_cache(maxsize=1)
def _get_agent() -> LoyaltyAgent:
    return LoyaltyAgent()


# ── Request models ─────────────────────────────────────────────────────────


class EarnPointsRequest(BaseModel):
    customer_id: str
    tier: str
    rule_type: str
    spend_amount: str  # DecimalString (I-05)
    reference_id: str = ""


class ApplyBonusRequest(BaseModel):
    customer_id: str
    points: str  # DecimalString
    reason: str
    reference_id: str = ""


class RedeemPointsRequest(BaseModel):
    customer_id: str
    option_id: str
    quantity: int = 1


class ProcessCashbackRequest(BaseModel):
    customer_id: str
    spend_amount: str  # DecimalString (I-05)
    mcc: str = "default"
    reference_id: str = ""


# ── Routes ─────────────────────────────────────────────────────────────────


@router.get("/v1/loyalty/balance/{customer_id}")
async def get_balance(customer_id: str) -> dict:
    """Get points balance and tier for a customer."""
    return _get_agent().get_balance(customer_id)


@router.post("/v1/loyalty/earn", status_code=201)
async def earn_points(req: EarnPointsRequest) -> dict:
    """Earn points from card spend, FX, or direct debit.

    Returns {"points_earned": str, "new_balance": str, "tier": str}.
    """
    try:
        return _get_agent().earn_points(
            customer_id=req.customer_id,
            tier_str=req.tier,
            rule_type_str=req.rule_type,
            spend_amount_str=req.spend_amount,
            reference_id=req.reference_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/v1/loyalty/bonus", status_code=201)
async def apply_bonus(req: ApplyBonusRequest) -> dict:
    """Apply a manual bonus. HITL_REQUIRED if >10,000 points (I-27)."""
    return _get_agent().apply_bonus(
        customer_id=req.customer_id,
        points_str=req.points,
        reason=req.reason,
        reference_id=req.reference_id,
    )


@router.get("/v1/loyalty/history/{customer_id}")
async def get_earn_history(customer_id: str, limit: int = 100) -> dict:
    """Get points transaction history for a customer."""
    return _get_agent().get_earn_history(customer_id, limit=limit)


@router.post("/v1/loyalty/redeem", status_code=201)
async def redeem_points(req: RedeemPointsRequest) -> dict:
    """Redeem points for a reward option.

    HTTP 422 if option not found or insufficient balance.
    """
    try:
        return _get_agent().redeem_points(
            customer_id=req.customer_id,
            option_id=req.option_id,
            quantity=req.quantity,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/v1/loyalty/options/{customer_id}")
async def list_redeem_options(customer_id: str) -> dict:
    """List active redemption options with affordability flag per customer balance."""
    return _get_agent().list_redeem_options(customer_id)


@router.get("/v1/loyalty/tier/{customer_id}/evaluate")
async def evaluate_tier(customer_id: str) -> dict:
    """Evaluate and apply tier upgrade/downgrade based on lifetime points."""
    return _get_agent().evaluate_tier(customer_id)


@router.get("/v1/loyalty/tiers")
async def list_tiers() -> dict:
    """List all tiers with thresholds and benefits."""
    return _get_agent().list_tiers()


@router.post("/v1/loyalty/cashback", status_code=201)
async def process_cashback(req: ProcessCashbackRequest) -> dict:
    """Process MCC-based cashback and convert to loyalty points.

    Returns {"cashback_amount": str, "points_earned": str, "new_balance": str}.
    """
    return _get_agent().process_cashback(
        customer_id=req.customer_id,
        spend_amount_str=req.spend_amount,
        mcc=req.mcc,
        reference_id=req.reference_id,
    )


@router.get("/v1/loyalty/expiry/{customer_id}")
async def get_expiry_forecast(customer_id: str, days_ahead: int = 30) -> dict:
    """Return points expiring within days_ahead days for a customer."""
    return _get_agent().get_expiry_forecast(customer_id, days_ahead=days_ahead)
