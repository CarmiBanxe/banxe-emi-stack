"""
api/routers/safeguarding_recon.py — Daily Safeguarding Reconciliation REST endpoints
IL-REC-01 | Phase 51B | Sprint 36 | CASS 7.15
5 endpoints: POST /v1/safeguarding-recon/run, GET /v1/safeguarding-recon/reports,
             GET /v1/safeguarding-recon/reports/{date}, GET /v1/safeguarding-recon/breaches,
             POST /v1/safeguarding-recon/breaches/{id}/resolve
Prefix is /v1/safeguarding-recon/* to avoid conflict with existing /v1/recon/*
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.recon.recon_agent import ReconAgent
from services.recon.reconciliation_engine_v2 import StatementEntry

router = APIRouter(tags=["Safeguarding Reconciliation"])

_agent = ReconAgent()


# ── Request/Response Models ───────────────────────────────────────────────────


class RunReconRequest(BaseModel):
    date_str: str
    ledger_entries: list[dict] = []
    statement_entries: list[dict] = []


class ReconciliationItemResponse(BaseModel):
    item_id: str
    account_iban: str
    ledger_amount: str  # Decimal as string (I-01)
    statement_amount: str
    discrepancy: str
    recon_date: str
    status: str


class ReconReportResponse(BaseModel):
    report_id: str
    recon_date: str
    total_ledger_gbp: str  # Decimal as string (I-01)
    total_statement_gbp: str
    net_discrepancy_gbp: str
    breach_detected: bool
    created_at: str
    items: list[ReconciliationItemResponse]


class HITLProposalResponse(BaseModel):
    action: str
    entity_id: str
    requires_approval_from: str
    reason: str
    autonomy_level: str


class ResolveBreachRequest(BaseModel):
    resolved_by: str


# ── Helpers ───────────────────────────────────────────────────────────────────


def _format_report(report: object) -> ReconReportResponse:
    items = [
        ReconciliationItemResponse(
            item_id=i.item_id,
            account_iban=i.account_iban,
            ledger_amount=str(i.ledger_amount),
            statement_amount=str(i.statement_amount),
            discrepancy=str(i.discrepancy),
            recon_date=i.recon_date,
            status=i.status,
        )
        for i in report.items  # type: ignore[union-attr]
    ]
    return ReconReportResponse(
        report_id=report.report_id,  # type: ignore[union-attr]
        recon_date=report.recon_date,  # type: ignore[union-attr]
        total_ledger_gbp=str(report.total_ledger_gbp),  # type: ignore[union-attr]
        total_statement_gbp=str(report.total_statement_gbp),  # type: ignore[union-attr]
        net_discrepancy_gbp=str(report.net_discrepancy_gbp),  # type: ignore[union-attr]
        breach_detected=report.breach_detected,  # type: ignore[union-attr]
        created_at=report.created_at,  # type: ignore[union-attr]
        items=items,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/safeguarding-recon/run")
async def run_reconciliation(
    request: RunReconRequest,
) -> ReconReportResponse | HITLProposalResponse:
    """L1/L4 — run daily reconciliation. Returns report or HITLProposal if breach >£100."""
    stmt_entries = [
        StatementEntry(
            entry_id=s.get("entry_id", "unknown"),
            account_iban=s["account_iban"],
            amount=Decimal(str(s["amount"])),
            currency=s.get("currency", "GBP"),
            value_date=s.get("value_date", ""),
            description=s.get("description", ""),
            transaction_ref=s.get("transaction_ref", ""),
        )
        for s in request.statement_entries
    ]
    result = _agent.run_daily_recon(request.date_str, request.ledger_entries, stmt_entries)
    if hasattr(result, "action"):  # HITLProposal
        return HITLProposalResponse(**result.__dict__)
    return _format_report(result)


@router.get("/safeguarding-recon/reports", response_model=list[ReconReportResponse])
async def list_reports() -> list[ReconReportResponse]:
    """L1 auto — list all reconciliation reports."""
    return [_format_report(r) for r in _agent.list_all_reports()]


@router.get("/safeguarding-recon/reports/{recon_date}", response_model=ReconReportResponse)
async def get_report(recon_date: str) -> ReconReportResponse:
    """L1 auto — get reconciliation report by date."""
    report = _agent.get_report(recon_date)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Report not found for {recon_date}")
    return _format_report(report)


@router.get("/safeguarding-recon/breaches", response_model=list[ReconReportResponse])
async def list_breaches() -> list[ReconReportResponse]:
    """L1 auto — list all breach reports."""
    return [_format_report(r) for r in _agent.list_unresolved_breaches()]


@router.post(
    "/safeguarding-recon/breaches/{report_id}/resolve", response_model=HITLProposalResponse
)
async def resolve_breach(report_id: str, request: ResolveBreachRequest) -> HITLProposalResponse:
    """L4 HITL — propose breach resolution. Returns HITLProposal (COMPLIANCE_OFFICER)."""
    from services.recon.reconciliation_engine_v2 import InMemoryReconStore, ReconciliationEngineV2

    engine = ReconciliationEngineV2(InMemoryReconStore())
    proposal = engine.resolve_breach(report_id, request.resolved_by)
    return HITLProposalResponse(**proposal.__dict__)
