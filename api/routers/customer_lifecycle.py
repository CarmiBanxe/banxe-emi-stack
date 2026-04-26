"""
api/routers/customer_lifecycle.py -- Customer Lifecycle FSM endpoints
IL-LCY-01 | banxe-emi-stack
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.customer_lifecycle.lifecycle_agent import LifecycleAgent
from services.customer_lifecycle.lifecycle_engine import LifecycleEngine
from services.customer_lifecycle.lifecycle_models import LifecycleEvent

logger = logging.getLogger("banxe.lifecycle")
router = APIRouter(tags=["CustomerLifecycle"])

_engine = LifecycleEngine()
_agent = LifecycleAgent(_engine)


class TransitionRequest(BaseModel):
    event: LifecycleEvent
    country: str = "GB"


class ReactivateRequest(BaseModel):
    officer: str
    reason: str


@router.post("/lifecycle/{customer_id}/transition", summary="Trigger lifecycle transition")
async def trigger_transition(customer_id: str, body: TransitionRequest):
    try:
        result = _engine.transition(customer_id, body.event, body.country)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if result is None:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid transition: {body.event.value} not allowed from current state",
        )
    return {
        "customer_id": result.customer_id,
        "from_state": result.from_state.value,
        "to_state": result.to_state.value,
        "event": result.event.value,
        "transitioned_at": result.transitioned_at,
    }


@router.get("/lifecycle/{customer_id}/state", summary="Current state and history")
async def get_lifecycle_state(customer_id: str):
    state = _engine.get_state(customer_id)
    history = _engine.get_history(customer_id)
    return {
        "customer_id": customer_id,
        "current_state": state.value,
        "transition_count": len(history),
        "history": [
            {
                "from": t.from_state.value,
                "to": t.to_state.value,
                "event": t.event.value,
                "at": t.transitioned_at,
            }
            for t in history
        ],
    }


@router.get("/lifecycle/dormant", summary="List dormant customers")
async def list_dormant():
    dormant = _engine.list_dormant()
    return {"dormant_count": len(dormant), "customer_ids": dormant}


@router.post(
    "/lifecycle/{customer_id}/reactivate",
    summary="Reactivate dormant customer (I-27 HITL L4)",
)
async def reactivate_customer(customer_id: str, body: ReactivateRequest):
    proposal = _agent.propose_reactivate(customer_id, body.reason)
    return {
        "status": "HITL_REQUIRED",
        "proposal_id": proposal.proposal_id,
        "customer_id": customer_id,
        "requires_approval_from": proposal.requires_approval_from,
        "approved": proposal.approved,
    }
