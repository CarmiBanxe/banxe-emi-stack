"""
api/routers/reporting.py — Compliance Reporting endpoints
IL-052 | Phase 3 | banxe-emi-stack

FIN060 (CASS 15.12.4R) — Monthly safeguarding return.
SAR    (POCA 2002 s.330) — Suspicious Activity Report filing with MLRO gate.

Endpoints:
  POST /v1/reporting/fin060/generate    — generate FIN060 PDF for a period
  POST /v1/reporting/fin060/submit      — submit FIN060 to FCA RegData
  POST /v1/reporting/sar                — file a draft SAR (MLRO review required)
  GET  /v1/reporting/sar                — list SARs (filter by status)
  GET  /v1/reporting/sar/stats          — SAR metrics for MLRO dashboard
  GET  /v1/reporting/sar/{sar_id}       — get single SAR
  POST /v1/reporting/sar/{sar_id}/approve  — MLRO approves SAR
  POST /v1/reporting/sar/{sar_id}/submit   — submit MLRO-approved SAR to NCA
  POST /v1/reporting/sar/{sar_id}/withdraw — MLRO withdraws SAR
"""
from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from typing import Optional

from fastapi import APIRouter, HTTPException

from api.models.reporting import (
    FileSARRequest,
    FIN060GenerateRequest,
    FIN060Response,
    MLRODecisionRequest,
    SARListResponse,
    SARResponse,
    SARStatsResponse,
    WithdrawSARRequest,
)
from services.aml.sar_service import SARService, SARServiceError, SARStatus
from services.reporting.regdata_return import RegDataReturnService, ReturnStatus

router = APIRouter(tags=["Compliance Reporting"])


# ── Service factories (overridable in tests via dependency_overrides) ──────────

@lru_cache(maxsize=1)
def _get_sar_service() -> SARService:
    return SARService()


@lru_cache(maxsize=1)
def _get_regdata_service() -> RegDataReturnService:
    return RegDataReturnService()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sar_to_response(sar) -> SARResponse:  # type: ignore[no-untyped-def]
    return SARResponse(
        sar_id=sar.sar_id,
        transaction_id=sar.transaction_id,
        customer_id=sar.customer_id,
        entity_type=sar.entity_type,
        amount=sar.amount,
        currency=sar.currency,
        sar_reasons=[r.value for r in sar.sar_reasons],
        aml_flags=sar.aml_flags,
        fraud_score=sar.fraud_score,
        status=sar.status,
        created_at=sar.created_at,
        created_by=sar.created_by,
        mlro_reviewed_by=sar.mlro_reviewed_by,
        mlro_reviewed_at=sar.mlro_reviewed_at,
        mlro_notes=sar.mlro_notes,
        submitted_at=sar.submitted_at,
        nca_reference=sar.nca_reference,
        errors=sar.errors,
        is_submittable=sar.is_submittable,
        requires_mlro_action=sar.requires_mlro_action,
    )


# ── FIN060 ────────────────────────────────────────────────────────────────────

@router.post(
    "/reporting/fin060/generate",
    response_model=FIN060Response,
    status_code=201,
    summary="Generate FIN060 safeguarding return (CASS 15.12.4R)",
)
def generate_fin060(body: FIN060GenerateRequest) -> FIN060Response:
    """
    Generate a FIN060 PDF for the given reporting period.
    The amounts supplied in the request body override the ClickHouse query
    when the stub generator is active (production: fetched from ClickHouse).
    """
    svc = _get_regdata_service()
    result = svc.run_monthly_return(
        period_start=body.period_start,
        period_end=body.period_end,
    )
    return FIN060Response(
        period_start=result.period_start,
        period_end=result.period_end,
        avg_daily_client_funds=Decimal(body.avg_daily_client_funds),
        peak_client_funds=Decimal(body.peak_client_funds),
        frn=result.frn,
        status=result.status.value,
        submission_id=result.submission_id,
        submitted_at=result.submitted_at,
        deadline=result.deadline,
        is_overdue=result.is_overdue,
        pdf_path=result.pdf_path,
        errors=result.errors,
    )


@router.post(
    "/reporting/fin060/submit",
    response_model=FIN060Response,
    summary="Submit FIN060 to FCA RegData (CASS 15.12.4R)",
)
def submit_fin060(body: FIN060GenerateRequest) -> FIN060Response:
    """
    Generate + submit FIN060 to FCA RegData in one call.
    STATUS: RegData submission is STUBBED until FCA_REGDATA_API_KEY is provisioned (CEO action).
    """
    svc = _get_regdata_service()
    result = svc.run_monthly_return(
        period_start=body.period_start,
        period_end=body.period_end,
    )
    if result.status == ReturnStatus.SUBMISSION_FAILED:
        raise HTTPException(
            status_code=502,
            detail=f"FIN060 submission failed: {'; '.join(result.errors)}",
        )
    return FIN060Response(
        period_start=result.period_start,
        period_end=result.period_end,
        avg_daily_client_funds=Decimal(body.avg_daily_client_funds),
        peak_client_funds=Decimal(body.peak_client_funds),
        frn=result.frn,
        status=result.status.value,
        submission_id=result.submission_id,
        submitted_at=result.submitted_at,
        deadline=result.deadline,
        is_overdue=result.is_overdue,
        pdf_path=result.pdf_path,
        errors=result.errors,
    )


# ── SAR ───────────────────────────────────────────────────────────────────────

@router.post(
    "/reporting/sar",
    response_model=SARResponse,
    status_code=201,
    summary="File a Suspicious Activity Report (POCA 2002 s.330)",
)
def file_sar(body: FileSARRequest) -> SARResponse:
    """
    Create a DRAFT SAR pending MLRO review.
    POCA 2002 s.330: must be filed when ML is known or suspected.
    The SAR cannot be submitted to NCA until MLRO approves it.
    """
    svc = _get_sar_service()
    sar = svc.file_sar(
        transaction_id=body.transaction_id,
        customer_id=body.customer_id,
        entity_type=body.entity_type,
        amount=Decimal(body.amount),
        currency=body.currency,
        sar_reasons=body.sar_reasons,
        aml_flags=body.aml_flags,
        fraud_score=body.fraud_score,
        created_by=body.created_by,
    )
    return _sar_to_response(sar)


@router.get(
    "/reporting/sar",
    response_model=SARListResponse,
    summary="List SARs",
)
def list_sars(status: Optional[SARStatus] = None) -> SARListResponse:
    """
    List all SARs, optionally filtered by status.
    GDPR: restricted to MLRO and compliance roles (enforced at auth layer).
    """
    svc = _get_sar_service()
    sars = svc.list_sars(status=status)
    return SARListResponse(
        sars=[_sar_to_response(s) for s in sars],
        total=len(sars),
    )


@router.get(
    "/reporting/sar/stats",
    response_model=SARStatsResponse,
    summary="SAR statistics for MLRO dashboard",
)
def sar_stats() -> SARStatsResponse:
    """Aggregated SAR metrics: counts by status + submission rate."""
    svc = _get_sar_service()
    s = svc.stats()
    return SARStatsResponse(
        total=s.total,
        draft=s.draft,
        mlro_approved=s.mlro_approved,
        submitted=s.submitted,
        submission_failed=s.submission_failed,
        withdrawn=s.withdrawn,
        submission_rate=s.submission_rate,
    )


@router.get(
    "/reporting/sar/{sar_id}",
    response_model=SARResponse,
    summary="Get SAR by ID",
)
def get_sar(sar_id: str) -> SARResponse:
    svc = _get_sar_service()
    sar = svc.get_sar(sar_id)
    if sar is None:
        raise HTTPException(status_code=404, detail=f"SAR {sar_id} not found")
    return _sar_to_response(sar)


@router.post(
    "/reporting/sar/{sar_id}/approve",
    response_model=SARResponse,
    summary="MLRO approves SAR for NCA submission (POCA 2002 s.330)",
)
def approve_sar(sar_id: str, body: MLRODecisionRequest) -> SARResponse:
    """
    MLRO gate: approve a DRAFT SAR for NCA submission.
    Only DRAFT SARs can be approved. Decision is logged for FCA audit (5-year retention).
    """
    svc = _get_sar_service()
    try:
        sar = svc.approve_sar(sar_id=sar_id, mlro_id=body.mlro_id, notes=body.notes)
    except SARServiceError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _sar_to_response(sar)


@router.post(
    "/reporting/sar/{sar_id}/submit",
    response_model=SARResponse,
    summary="Submit MLRO-approved SAR to NCA SAROnline",
)
def submit_sar(sar_id: str) -> SARResponse:
    """
    Submit an MLRO-approved SAR to NCA SAROnline.
    Requires status=MLRO_APPROVED — POCA 2002 s.330 MLRO gate is mandatory.
    STATUS: NCA SAROnline is STUBBED until NCA credentials are provisioned.
    """
    svc = _get_sar_service()
    try:
        sar = svc.submit_sar(sar_id=sar_id)
    except SARServiceError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _sar_to_response(sar)


@router.post(
    "/reporting/sar/{sar_id}/withdraw",
    response_model=SARResponse,
    summary="MLRO withdraws SAR (JMLSG §6.7)",
)
def withdraw_sar(sar_id: str, body: WithdrawSARRequest) -> SARResponse:
    """
    MLRO concludes transaction is not suspicious — SAR withdrawn.
    Withdrawal reason is mandatory (JMLSG guidance §6.7).
    Can only withdraw DRAFT or MLRO_APPROVED SARs.
    """
    svc = _get_sar_service()
    try:
        sar = svc.withdraw_sar(sar_id=sar_id, mlro_id=body.mlro_id, reason=body.reason)
    except SARServiceError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _sar_to_response(sar)
