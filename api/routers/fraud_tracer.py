"""
api/routers/fraud_tracer.py — Fraud Transaction Tracer endpoints
IL-TRC-01 | banxe-emi-stack
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

from services.fraud_tracer.tracer_agent import FraudHITLProposal, FraudTracerAgent
from services.fraud_tracer.tracer_engine import TracerEngine
from services.fraud_tracer.tracer_models import TraceRequest
from services.fraud_tracer.velocity_checker import VelocityChecker

logger = logging.getLogger("banxe.fraud_tracer")
router = APIRouter(tags=["FraudTracer"])

_engine = TracerEngine()
_agent = FraudTracerAgent(_engine)
_velocity = VelocityChecker()


class UpdateRulesRequest(BaseModel):
    officer: str
    reason: str
    max_tx_count: int | None = None
    max_tx_amount: str | None = None


@router.post("/fraud-tracer/trace", summary="Trace transaction for fraud (real-time)")
async def trace_transaction(body: TraceRequest):
    result = _agent.trace_and_decide(body)
    if isinstance(result, FraudHITLProposal):
        return {
            "status": "HITL_REQUIRED",
            "proposal_id": result.proposal_id,
            "score": result.score,
            "flags": result.flags,
            "requires_approval_from": result.requires_approval_from,
        }
    return {
        "transaction_id": result.transaction_id,
        "score": result.score,
        "flags": result.flags,
        "status": result.status,
        "latency_ms": result.latency_ms,
    }


@router.get("/fraud-tracer/history/{tx_id}", summary="Fraud trace history for transaction")
async def get_trace_history(tx_id: str):
    history = [e for e in _engine.trace_log if e["transaction_id"] == tx_id]
    return {"transaction_id": tx_id, "history": history}


@router.get("/fraud-tracer/velocity/{customer_id}", summary="Velocity status for customer")
async def get_velocity_status(customer_id: str):
    result = _velocity.check_velocity(customer_id)
    return {
        "customer_id": result.customer_id,
        "tx_count": result.tx_count,
        "total_amount": result.total_amount,
        "breached": result.breached,
        "window_minutes": result.window_minutes,
    }


@router.post(
    "/fraud-tracer/rules/update",
    summary="Update fraud rules (I-27 HITL L4 — FRAUD_ANALYST required)",
)
async def update_fraud_rules(body: UpdateRulesRequest):
    # I-27: rule changes require human officer — propose only
    return {
        "status": "HITL_REQUIRED",
        "action": "fraud_rules_update",
        "requested_by": body.officer,
        "reason": body.reason,
        "requires_approval_from": "FRAUD_ANALYST",
        "approved": False,
    }


@router.get("/fraud-tracer/dashboard", summary="Fraud tracer dashboard")
async def get_fraud_dashboard():
    log = _engine.trace_log
    total = len(log)
    blocked = sum(1 for e in log if e["status"] == "BLOCK")
    review = sum(1 for e in log if e["status"] == "REVIEW")
    clear = sum(1 for e in log if e["status"] == "CLEAR")
    return {
        "total_traced": total,
        "blocked": blocked,
        "review": review,
        "clear": clear,
        "pending_proposals": len(_agent.proposals),
    }
