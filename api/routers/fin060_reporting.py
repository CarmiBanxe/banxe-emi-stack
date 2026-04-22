"""
api/routers/fin060_reporting.py — FIN060 Regulatory Reporting REST endpoints
IL-FIN060-01 | Phase 51C | Sprint 36
5 endpoints: POST /v1/fin060/generate, GET /v1/fin060/{year}/{month},
             GET /v1/fin060/history, POST /v1/fin060/{id}/approve,
             GET /v1/fin060/dashboard
Prefix is /v1/fin060/* to avoid conflict with existing /v1/reporting/*
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.reporting.reporting_agent import ReportingAgent

router = APIRouter(tags=["FIN060 Reporting"])

_agent = ReportingAgent()


# ── Request/Response Models ───────────────────────────────────────────────────


class GenerateRequest(BaseModel):
    month: int
    year: int
    ledger_data: list[dict] = []


class HITLProposalResponse(BaseModel):
    action: str
    entity_id: str
    requires_approval_from: str
    reason: str
    autonomy_level: str


class FIN060ReportResponse(BaseModel):
    report_id: str
    month: int
    year: int
    total_safeguarded_gbp: str  # Decimal as string (I-01)
    total_operational_gbp: str
    status: str
    generated_at: str
    approved_by: str | None


class ApproveRequest(BaseModel):
    approved_by: str


# ── Helpers ───────────────────────────────────────────────────────────────────


def _format_report(report: object) -> FIN060ReportResponse:
    return FIN060ReportResponse(
        report_id=report.report_id,  # type: ignore[union-attr]
        month=report.month,  # type: ignore[union-attr]
        year=report.year,  # type: ignore[union-attr]
        total_safeguarded_gbp=str(report.total_safeguarded_gbp),  # type: ignore[union-attr]
        total_operational_gbp=str(report.total_operational_gbp),  # type: ignore[union-attr]
        status=report.status,  # type: ignore[union-attr]
        generated_at=report.generated_at,  # type: ignore[union-attr]
        approved_by=report.approved_by,  # type: ignore[union-attr]
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/fin060/generate", response_model=HITLProposalResponse)
async def generate_fin060(request: GenerateRequest) -> HITLProposalResponse:
    """L4 HITL — generate FIN060 report. Returns HITLProposal (CFO)."""
    try:
        proposal = _agent.run_monthly_fin060(request.month, request.year, request.ledger_data)
        return HITLProposalResponse(**proposal.__dict__)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/fin060/{year}/{month}", response_model=FIN060ReportResponse)
async def get_report(year: int, month: int) -> FIN060ReportResponse:
    """L1 auto — get FIN060 report by year/month."""
    report = _agent.get_report(month, year)
    if report is None:
        raise HTTPException(
            status_code=404, detail=f"FIN060 report not found for {year}-{month:02d}"
        )
    return _format_report(report)


@router.get("/fin060/history", response_model=list[FIN060ReportResponse])
async def list_history() -> list[FIN060ReportResponse]:
    """L1 auto — list all FIN060 reports."""
    reports = _agent._generator._store.list_reports()  # noqa: SLF001
    return [_format_report(r) for r in reports]


@router.post("/fin060/{report_id}/approve", response_model=HITLProposalResponse)
async def approve_report(report_id: str, request: ApproveRequest) -> HITLProposalResponse:
    """L4 HITL — approve FIN060 report. Returns HITLProposal (CFO)."""
    proposal = _agent.approve_and_submit(report_id, request.approved_by)
    return HITLProposalResponse(**proposal.__dict__)


@router.get("/fin060/dashboard")
async def get_dashboard() -> dict:
    """L1 auto — return FIN060 dashboard summary."""
    return _agent.get_dashboard()
