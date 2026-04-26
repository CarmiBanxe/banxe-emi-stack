"""
api/routers/complaints.py — FCA DISP Complaints endpoints
IL-DSP-01 | banxe-emi-stack
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.complaints.complaints_agent import ComplaintsAgent, ComplaintsHITLProposal
from services.complaints.complaints_engine import ComplaintsEngine
from services.complaints.complaints_models import ComplaintCategory

logger = logging.getLogger("banxe.complaints")
router = APIRouter(tags=["Complaints"])

_engine = ComplaintsEngine()
_agent = ComplaintsAgent(_engine)


class RegisterRequest(BaseModel):
    customer_id: str
    category: ComplaintCategory
    description: str


class ResolveRequest(BaseModel):
    outcome: str
    redress_amount: str = "0.00"


@router.post("/complaints", status_code=201, summary="Register FCA DISP complaint")
async def register_complaint(body: RegisterRequest):  # type: ignore[return]
    complaint = _engine.register(body.customer_id, body.category, body.description)
    return {
        "complaint_id": complaint.complaint_id,
        "status": complaint.status.value,
        "sla_days": complaint.sla_days,
        "registered_at": complaint.registered_at,
    }


@router.get("/complaints/dashboard", summary="Complaints dashboard")
async def complaints_dashboard():  # type: ignore[return]
    all_c = _engine._store.list_all()
    by_status: dict[str, int] = {}
    for c in all_c:
        key = c.status.value
        by_status[key] = by_status.get(key, 0) + 1
    return {
        "total": len(all_c),
        "by_status": by_status,
        "total_resolutions": len(_engine.resolutions),
        "pending_proposals": len(_agent.proposals),
    }


@router.get("/complaints/sla-breaches", summary="List approaching SLA breaches")
async def list_sla_breaches():  # type: ignore[return]
    approaching = _engine.get_sla_approaching()
    return {
        "count": len(approaching),
        "complaints": [
            {"complaint_id": c.complaint_id, "status": c.status.value, "sla_days": c.sla_days}
            for c in approaching
        ],
    }


@router.get("/complaints/{complaint_id}", summary="Get complaint status")
async def get_complaint(complaint_id: str):  # type: ignore[return]
    complaint = _engine._store.get_by_id(complaint_id)
    if complaint is None:
        raise HTTPException(status_code=404, detail="Complaint not found")
    return {
        "complaint_id": complaint.complaint_id,
        "status": complaint.status.value,
        "category": complaint.category.value,
        "sla_days": complaint.sla_days,
    }


@router.post(
    "/complaints/{complaint_id}/resolve",
    summary="Resolve complaint (I-27 HITL if redress > £500)",
)
async def resolve_complaint(complaint_id: str, body: ResolveRequest):  # type: ignore[return]
    result = _agent.resolve_with_redress(complaint_id, body.outcome, body.redress_amount)
    if isinstance(result, ComplaintsHITLProposal):
        return {
            "status": "HITL_REQUIRED",
            "proposal_id": result.proposal_id,
            "reason": result.reason,
            "requires_approval_from": result.requires_approval_from,
        }
    return {
        "complaint_id": result.complaint_id,
        "outcome": result.outcome,
        "redress_amount": result.redress_amount,
        "resolved_at": result.resolved_at,
    }
