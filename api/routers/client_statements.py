"""
api/routers/client_statements.py -- Client Statement endpoints
IL-CST-01 | banxe-emi-stack
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.client_statements.statement_agent import StatementAgent
from services.client_statements.statement_generator import StatementGenerator
from services.client_statements.statement_models import StatementFormat

logger = logging.getLogger("banxe.statements")
router = APIRouter(tags=["ClientStatements"])

_generator = StatementGenerator()
_agent = StatementAgent(_generator)


class GenerateRequest(BaseModel):
    customer_id: str
    period_start: str
    period_end: str
    format: StatementFormat = StatementFormat.JSON


class CorrectRequest(BaseModel):
    reason: str
    officer: str


@router.post("/statements/generate", status_code=201, summary="Generate client statement")
async def generate_statement(body: GenerateRequest):
    stmt = _generator.generate(body.customer_id, body.period_start, body.period_end, body.format)
    return {
        "statement_id": stmt.statement_id,
        "customer_id": stmt.customer_id,
        "period_start": stmt.period_start,
        "period_end": stmt.period_end,
        "format": stmt.format.value,
        "entry_count": len(stmt.entries),
        "generated_at": stmt.generated_at,
    }


@router.get("/statements/{customer_id}/history", summary="Statement history for customer")
async def get_statement_history(customer_id: str):
    log = [e for e in _generator.statement_log if e.get("customer_id") == customer_id]
    return {"customer_id": customer_id, "statement_count": len(log), "statements": log}


@router.get("/statements/{statement_id}/download", summary="Download statement (PDF/CSV/JSON)")
async def download_statement(statement_id: str):
    log_entry = next(
        (e for e in _generator.statement_log if e.get("statement_id") == statement_id),
        None,
    )
    if not log_entry:
        raise HTTPException(status_code=404, detail="Statement not found")
    return {
        "statement_id": statement_id,
        "download_url": f"/files/statements/{statement_id}",
        "status": "ready",
    }


@router.post(
    "/statements/{statement_id}/correct",
    summary="Correct statement (I-27 HITL L4 -- OPERATIONS_OFFICER required)",
)
async def correct_statement(statement_id: str, body: CorrectRequest):
    proposal = _agent.propose_correction(statement_id, body.reason)
    return {
        "status": "HITL_REQUIRED",
        "proposal_id": proposal.proposal_id,
        "requires_approval_from": proposal.requires_approval_from,
        "approved": proposal.approved,
    }
