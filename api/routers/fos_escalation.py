"""
api/routers/fos_escalation.py -- FOS Escalation endpoints
IL-FOS-01 | banxe-emi-stack
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

from services.complaints.fos_escalation import FOSEscalation

logger = logging.getLogger("banxe.fos")
router = APIRouter(tags=["FOSEscalation"])

_fos = FOSEscalation()


class PrepareRequest(BaseModel):
    customer_id: str
    weeks_elapsed: int
    firm_decision: str = "not_upheld"


@router.post("/fos/prepare/{complaint_id}", status_code=201, summary="Prepare FOS case package")
async def prepare_fos_case(complaint_id: str, body: PrepareRequest):
    package = _fos.prepare_case(
        complaint_id=complaint_id,
        customer_id=body.customer_id,
        weeks_elapsed=body.weeks_elapsed,
        firm_decision=body.firm_decision,
    )
    return {
        "case_id": package.case_id,
        "complaint_id": package.complaint_id,
        "status": package.status.value,
        "weeks_since_complaint": package.weeks_since_complaint,
        "prepared_at": package.prepared_at,
    }


@router.get("/fos/cases", summary="List FOS cases")
async def list_fos_cases():
    cases = _fos._store.list_all()
    flagged = _fos.get_week6_flagged()
    return {
        "total": len(cases),
        "week6_flagged": len(flagged),
        "cases": [
            {
                "case_id": c.case_id,
                "complaint_id": c.complaint_id,
                "status": c.status.value,
                "weeks_elapsed": c.weeks_since_complaint,
            }
            for c in cases
        ],
    }


@router.post(
    "/fos/submit/{case_id}",
    summary="Submit case to FOS (I-27 HITL L4 -- dual sign-off required)",
)
async def submit_fos_case(case_id: str):
    result = _fos.submit_case(case_id)
    from services.complaints.fos_escalation import FOSHITLProposal

    if isinstance(result, FOSHITLProposal):
        return {
            "status": "HITL_REQUIRED",
            "proposal_id": result.proposal_id,
            "requires_approval_from": result.requires_approval_from,
            "approved": result.approved,
        }
    return {"case_id": case_id, "submitted": result.submitted}
