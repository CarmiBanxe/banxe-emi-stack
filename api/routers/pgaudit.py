"""
api/routers/pgaudit.py — pgAudit REST endpoints
IL-PGA-01 | Phase 51A | Sprint 36
5 endpoints: GET /v1/audit/logs, GET /v1/audit/logs/{db_name},
             GET /v1/audit/stats, POST /v1/audit/export, GET /v1/audit/health
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.audit.audit_query import AuditQueryService
from services.audit.pgaudit_config import InMemoryAuditLogPort

router = APIRouter(tags=["pgAudit"])

_service = AuditQueryService(port=InMemoryAuditLogPort())


# ── Response Models ───────────────────────────────────────────────────────────


class AuditEntryResponse(BaseModel):
    entry_id: str
    db_name: str
    table_name: str
    operation: str
    actor: str
    timestamp: str
    row_count: int
    success: bool


class AuditStatsResponse(BaseModel):
    db_name: str
    total_writes: int
    total_ddl: int
    last_24h_writes: int
    last_failure: str | None


class HITLProposalResponse(BaseModel):
    action: str
    entity_id: str
    requires_approval_from: str
    reason: str
    autonomy_level: str


class ExportRequest(BaseModel):
    db_name: str
    start_date: str
    end_date: str
    requested_by: str


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/audit/logs", response_model=list[AuditEntryResponse])
async def get_audit_logs(
    db_name: str = "banxe_core",
    start_date: str = "2020-01-01",
    end_date: str = "2099-12-31",
    limit: int = 100,
) -> list[AuditEntryResponse]:
    """L2 auto — query audit logs across all databases."""
    try:
        entries = _service.query_audit_log(db_name, None, start_date, end_date, limit)
        return [AuditEntryResponse(**e.__dict__) for e in entries]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/audit/logs/{db_name}", response_model=list[AuditEntryResponse])
async def get_audit_logs_by_db(
    db_name: str,
    start_date: str = "2020-01-01",
    end_date: str = "2099-12-31",
    limit: int = 100,
) -> list[AuditEntryResponse]:
    """L2 auto — query audit logs for a specific database."""
    try:
        entries = _service.query_audit_log(db_name, None, start_date, end_date, limit)
        return [AuditEntryResponse(**e.__dict__) for e in entries]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/audit/stats", response_model=list[AuditStatsResponse])
async def get_audit_stats() -> list[AuditStatsResponse]:
    """L2 auto — get stats for all databases."""
    stats = _service.get_all_stats()
    return [AuditStatsResponse(**s.__dict__) for s in stats]


@router.post("/audit/export", response_model=HITLProposalResponse)
async def export_audit_report(request: ExportRequest) -> HITLProposalResponse:
    """L4 HITL — propose audit export. Returns HITLProposal (COMPLIANCE_OFFICER)."""
    try:
        proposal = _service.export_audit_report(
            request.db_name,
            request.start_date,
            request.end_date,
            request.requested_by,
        )
        return HITLProposalResponse(**proposal.__dict__)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/audit/health")
async def audit_health() -> dict:
    """L1 auto — pgAudit health check."""
    return _service.health_check()
