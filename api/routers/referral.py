"""
api/routers/referral.py — Referral Program REST API
IL-REF-01 | Phase 30 | banxe-emi-stack

Endpoints (prefix /v1/referral embedded):
  POST /v1/referral/codes                             — generate referral code
  POST /v1/referral/track                             — track a referral (fraud check)
  POST /v1/referral/{referral_id}/advance             — advance referral status
  POST /v1/referral/{referral_id}/rewards             — distribute rewards (HITL if fraud, I-27)
  GET  /v1/referral/{referral_id}/status              — get referral status
  GET  /v1/referral/campaigns/{campaign_id}/stats     — campaign budget stats
  GET  /v1/referral/campaigns                         — list active campaigns
  GET  /v1/referral/rewards/{customer_id}/summary     — customer reward summary
  POST /v1/referral/{referral_id}/fraud-check         — run / re-run fraud check

FCA: COBS 4 (financial promotions), PS22/9 (fair value), BCOBS 2.2 (communications)
Invariants: I-01 (Decimal amounts), I-05 (amounts as strings), I-27 (HITL fraud-blocked)
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.intent_layer.shadow import maybe_mirror_intent
from services.referral.referral_agent import ReferralAgent

router = APIRouter(tags=["referral"])


@lru_cache(maxsize=1)
def _get_agent() -> ReferralAgent:
    return ReferralAgent()


# ── Request models ─────────────────────────────────────────────────────────


class GenerateCodeRequest(BaseModel):
    customer_id: str
    campaign_id: str = "camp-default"
    vanity_suffix: str = ""


class TrackReferralRequest(BaseModel):
    referee_id: str
    code: str
    ip_address: str = "0.0.0.0"  # noqa: S104  # nosec B104
    device_id: str = ""


class AdvanceReferralRequest(BaseModel):
    new_status: str


class DistributeRewardsRequest(BaseModel):
    ip_address: str = "0.0.0.0"  # noqa: S104  # nosec B104


class FraudCheckRequest(BaseModel):
    referrer_id: str
    referee_id: str
    ip_address: str
    device_id: str = ""


# ── Routes ─────────────────────────────────────────────────────────────────


@router.post("/v1/referral/codes", status_code=201)
async def generate_code(req: GenerateCodeRequest) -> dict:
    """Generate a unique referral code for a customer.

    Returns {"code_id", "customer_id", "code", "campaign_id", "is_vanity", "created_at"}.
    """
    try:
        return _get_agent().generate_code(
            customer_id=req.customer_id,
            campaign_id=req.campaign_id,
            vanity_suffix=req.vanity_suffix,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/v1/referral/track", status_code=201)
async def track_referral(req: TrackReferralRequest) -> dict:
    """Register a referral using a code. Runs fraud check automatically.

    Returns {"referral_id", "referrer_id", "referee_id", "status", "fraud_flagged"}.
    HTTP 422 on invalid code, self-referral, or already-referred customer.
    """
    try:
        result = _get_agent().track_referral(
            referee_id=req.referee_id,
            code_str=req.code,
            ip_address=req.ip_address,
            device_id=req.device_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    # FU-2 Phase 8: production shadow-mode. Fire-and-forget — mirrors a sampled slice of
    # this intent-like request into the Intent Layer (classify-only, no live action) and
    # logs how its decision compares to this mechanistic baseline. A no-op unless
    # INTENT_LAYER_SHADOW_ENABLED_PROD=true in production; never alters this response. The
    # descriptor is a non-PII endpoint label, never referee/IP/device data (R-SEC).
    maybe_mirror_intent(
        "referral",
        baseline_capability="Referral / CRM",
        correlation_id=result.get("referral_id"),
    )
    return result


@router.post("/v1/referral/{referral_id}/advance")
async def advance_referral(referral_id: str, req: AdvanceReferralRequest) -> dict:
    """Advance referral status through lifecycle.

    Valid transitions: INVITED→REGISTERED, REGISTERED→KYC_COMPLETE, KYC_COMPLETE→QUALIFIED.
    HTTP 422 on invalid transition or referral not found.
    """
    try:
        return _get_agent().advance_referral(referral_id, req.new_status)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/v1/referral/{referral_id}/rewards", status_code=201)
async def distribute_rewards(referral_id: str, req: DistributeRewardsRequest) -> dict:
    """Distribute rewards for a QUALIFIED referral.

    Returns HITL_REQUIRED if fraud-blocked (I-27).
    HTTP 422 if referral not QUALIFIED or campaign budget exhausted.
    """
    try:
        return _get_agent().distribute_rewards(
            referral_id=referral_id,
            ip_address=req.ip_address,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/v1/referral/{referral_id}/status")
async def get_referral_status(referral_id: str) -> dict:
    """Get current status and details of a referral.

    HTTP 422 if referral not found.
    """
    try:
        return _get_agent().get_referral_status(referral_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/v1/referral/campaigns/{campaign_id}/stats")
async def get_campaign_stats(campaign_id: str) -> dict:
    """Return campaign budget and statistics.

    HTTP 422 if campaign not found.
    """
    try:
        return _get_agent().get_campaign_stats(campaign_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/v1/referral/campaigns")
async def list_active_campaigns() -> dict:
    """List all currently ACTIVE referral campaigns."""
    return _get_agent().list_active_campaigns()


@router.get("/v1/referral/rewards/{customer_id}/summary")
async def get_reward_summary(customer_id: str) -> dict:
    """Return total earned/pending/paid rewards for a customer."""
    return _get_agent().get_reward_summary(customer_id)


@router.post("/v1/referral/{referral_id}/fraud-check")
async def run_fraud_check(referral_id: str, req: FraudCheckRequest) -> dict:
    """Run a fraud check on a referral and return the result."""
    return _get_agent().check_fraud(
        referral_id=referral_id,
        referrer_id=req.referrer_id,
        referee_id=req.referee_id,
        ip_address=req.ip_address,
        device_id=req.device_id,
    )
