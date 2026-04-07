"""
n8n_webhook.py — FastAPI endpoint: POST /complaints/new
IL-022 | FCA Consumer Duty DISP | banxe-emi-stack

WHY THIS EXISTS
---------------
Entry point for complaints received via API or Telegram bot.
Accepts complaint payload, calls ComplaintService.open_complaint(),
and returns complaint_id + SLA deadline. n8n polls /complaints/sla-check
daily for breach detection.

CTX-03 AMBER — public-facing endpoint, validates input strictly
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from services.config import CLICKHOUSE_HOST, CLICKHOUSE_PORT, CLICKHOUSE_DB
from services.complaints.complaint_service import (
    ComplaintService,
    ClickHouseComplaintRepository,
    SLABreach,
    SLAWarning,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Banxe Complaints API",
    description="FCA Consumer Duty DISP complaint intake and SLA monitoring",
    version="1.0.0",
)


# ─── Request / Response models ────────────────────────────────────────────────

class ComplaintRequest(BaseModel):
    customer_id: str = Field(..., min_length=1, max_length=128)
    category: str = Field(..., pattern="^(PAYMENT|ACCOUNT|CHARGES|SERVICE|FRAUD|DATA_PRIVACY|OTHER)$")
    description: str = Field(..., min_length=10, max_length=2000)
    channel: str = Field(default="API", pattern="^(TELEGRAM|EMAIL|PHONE|WEB|API)$")
    created_by: str = Field(default="system", max_length=64)


class ComplaintResponse(BaseModel):
    complaint_id: str
    sla_deadline: str  # ISO date string
    message: str


class SLACheckResponse(BaseModel):
    breaches: int
    warnings: int
    breach_ids: List[str]
    warning_ids: List[str]


class ResolveRequest(BaseModel):
    resolution_summary: str = Field(..., min_length=5, max_length=2000)
    actor: str = Field(default="system", max_length=64)


class FosEscalateRequest(BaseModel):
    fos_reference: str = Field(default="", max_length=64)
    actor: str = Field(default="system", max_length=64)


# ─── Service factory ──────────────────────────────────────────────────────────

def _get_service() -> ComplaintService:
    try:
        from clickhouse_driver import Client
        ch = Client(
            host=CLICKHOUSE_HOST,
            port=CLICKHOUSE_PORT,
            database=CLICKHOUSE_DB,
        )
        repo = ClickHouseComplaintRepository(ch)
    except ImportError:
        raise HTTPException(status_code=503, detail="ClickHouse driver not available")
    return ComplaintService(repo)


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.post("/complaints/new", response_model=ComplaintResponse, status_code=201)
def create_complaint(req: ComplaintRequest):
    """
    Open a new complaint. Returns complaint_id and SLA deadline (56 days).
    FCA DISP 1.4.1R — 8-week resolution window starts from this timestamp.
    """
    svc = _get_service()
    complaint_id = svc.open_complaint(
        customer_id=req.customer_id,
        category=req.category,
        description=req.description,
        channel=req.channel,
        created_by=req.created_by,
    )
    from datetime import timedelta
    sla_deadline = datetime.now(timezone.utc) + timedelta(days=56)
    return ComplaintResponse(
        complaint_id=complaint_id,
        sla_deadline=sla_deadline.date().isoformat(),
        message="Complaint registered. SLA: 8 weeks (DISP 1.4.1R).",
    )


@app.get("/complaints/sla-check", response_model=SLACheckResponse)
def sla_check():
    """
    Called by n8n cron daily at 09:00.
    Returns SLA breaches (overdue) and warnings (within 7 days of deadline).
    """
    svc = _get_service()
    breaches: List[SLABreach] = svc.check_sla_breaches()
    warnings: List[SLAWarning] = svc.check_sla_warnings()
    return SLACheckResponse(
        breaches=len(breaches),
        warnings=len(warnings),
        breach_ids=[b.complaint_id for b in breaches],
        warning_ids=[w.complaint_id for w in warnings],
    )


@app.post("/complaints/{complaint_id}/resolve", status_code=200)
def resolve_complaint(complaint_id: str, req: ResolveRequest):
    """Mark complaint as RESOLVED."""
    svc = _get_service()
    svc.resolve_complaint(
        complaint_id=complaint_id,
        resolution_summary=req.resolution_summary,
        actor=req.actor,
    )
    return {"resolved": True, "complaint_id": complaint_id}


@app.post("/complaints/{complaint_id}/escalate-fos", status_code=200)
def escalate_to_fos(complaint_id: str, req: FosEscalateRequest):
    """
    Escalate to Financial Ombudsman Service.
    FCA DISP 1.4.1R — mandatory if unresolved at 8 weeks.
    """
    svc = _get_service()
    svc.escalate_to_fos(
        complaint_id=complaint_id,
        fos_reference=req.fos_reference,
        actor=req.actor,
    )
    return {"escalated": True, "complaint_id": complaint_id}


@app.get("/health")
def health():
    return {"status": "ok", "service": "complaints"}
