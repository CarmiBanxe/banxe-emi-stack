"""
api/routers/ato_prevention.py — ATO Prevention endpoints
IL-ATO-01 | banxe-emi-stack
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

from services.ato_prevention.ato_agent import ATOAgent, ATOHITLProposal
from services.ato_prevention.ato_engine import ATOEngine
from services.ato_prevention.ato_models import GeoLocation, LoginAttempt

logger = logging.getLogger("banxe.ato")
router = APIRouter(tags=["ATOPrevention"])

_engine = ATOEngine()
_agent = ATOAgent(_engine)


class AssessLoginRequest(BaseModel):
    customer_id: str
    ip_address: str
    device_fingerprint: str
    country: str = "GB"
    city: str = ""
    success: bool = True


class UnlockRequest(BaseModel):
    officer: str
    reason: str


@router.post("/ato/assess", summary="Assess login attempt for ATO risk")
async def assess_login(body: AssessLoginRequest):  # type: ignore[return]
    attempt = LoginAttempt(
        customer_id=body.customer_id,
        ip_address=body.ip_address,
        device_fingerprint=body.device_fingerprint,
        geo=GeoLocation(country=body.country, city=body.city),
        success=body.success,
    )
    result = _agent.assess_and_act(attempt)
    if isinstance(result, ATOHITLProposal):
        return {
            "status": "HITL_REQUIRED",
            "proposal_id": result.proposal_id,
            "risk_score": result.risk_score,
            "reason": result.reason,
            "requires_approval_from": result.requires_approval_from,
        }
    return {
        "customer_id": result.customer_id,
        "risk_score": result.risk_score,
        "signals": result.signals,
        "action": result.action,
    }


@router.get("/ato/history/{customer_id}", summary="Login attempt history")
async def get_ato_history(customer_id: str):  # type: ignore[return]
    log = [e for e in _engine.ato_log if e.get("customer_id") == customer_id]
    return {"customer_id": customer_id, "history": log}


@router.post("/ato/unlock/{customer_id}", summary="Unlock account (I-27 HITL L4)")
async def unlock_account(customer_id: str, body: UnlockRequest):  # type: ignore[return]
    proposal = _agent.propose_unlock(customer_id, body.officer)
    return {
        "status": "HITL_REQUIRED",
        "proposal_id": proposal.proposal_id,
        "customer_id": customer_id,
        "requires_approval_from": proposal.requires_approval_from,
    }
