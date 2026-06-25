"""
api/routers/gabriel.py — K-gabriel FCA Returns Governance API
IL-CBS-GABRIEL-API-2026-06-26 | K-gabriel spec §5

Endpoints:
  GET  /v1/gabriel/returns                       — list all submission records
  GET  /v1/gabriel/returns/{submission_id}       — get by submission_id
  POST /v1/gabriel/returns                       — create or get idempotent draft
  POST /v1/gabriel/returns/{id}/approve          — HITL: approve → submit to FCA
  POST /v1/gabriel/returns/{id}/reject           — HITL: reject draft
  GET  /v1/gabriel/deadline/{return_type}/{period} — deadline status

FCA compliance:
  - I-27: approve endpoint is the ONLY path to GabrielSubmissionPort.submit()
  - I-24: all transitions audit-logged via GabrielAuditPort
  - I-08: audit TTL ≥ 5 years (enforced at persistence layer)
  - All amounts Decimal strings (none at this layer — structural data only)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from api.models.gabriel import (
    ApproveRequest,
    CreateDraftRequest,
    DeadlineStatusResponse,
    RejectRequest,
    SubmissionRecordResponse,
)
from services.gabriel.gabriel_models import (
    GabrielReturnType,
    InMemoryGabrielAuditPort,
    InMemoryGabrielSubmissionPort,
    SubmissionRecord,
)
from services.gabriel.returns_governor import ReturnsGovernor

logger = logging.getLogger("banxe.api.gabriel")

router = APIRouter(tags=["Gabriel Returns (K-gabriel)"])

# ── Singletons (sandbox InMemory; swap for real adapters in production) ───────

_governor = ReturnsGovernor(audit=InMemoryGabrielAuditPort())
_submission_port = InMemoryGabrielSubmissionPort()


# ── Helpers ───────────────────────────────────────────────────────────────────


def _to_response(record: SubmissionRecord) -> SubmissionRecordResponse:
    return SubmissionRecordResponse(
        submission_id=record.submission_id,
        return_type=record.return_type.value,
        return_period=record.return_period,
        fca_item_code=record.fca_item_code,
        prepared_at=record.prepared_at,
        validated_by=record.validated_by,
        status=record.status.value,
        idempotency_key=record.idempotency_key,
        submitted_at=record.submitted_at,
        submission_ref=record.submission_ref,
        source_recon_id=record.source_recon_id,
    )


def _parse_return_type(raw: str) -> GabrielReturnType:
    try:
        return GabrielReturnType(raw.upper())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown return_type {raw!r}. Valid values: FIN060, BREACH_REPORT",
        )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/gabriel/returns", response_model=list[SubmissionRecordResponse])
async def list_gabriel_returns() -> list[SubmissionRecordResponse]:
    """List all K-gabriel submission records."""
    return [_to_response(r) for r in _governor.list_records()]


@router.get(
    "/gabriel/returns/{submission_id}", response_model=SubmissionRecordResponse
)
async def get_gabriel_return(submission_id: str) -> SubmissionRecordResponse:
    """Get a single submission record by submission_id."""
    record = _governor.get_by_id(submission_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No submission record with id={submission_id!r}",
        )
    return _to_response(record)


@router.post(
    "/gabriel/returns",
    response_model=SubmissionRecordResponse,
    status_code=status.HTTP_200_OK,
)
async def create_gabriel_draft(body: CreateDraftRequest) -> SubmissionRecordResponse:
    """Create or retrieve an idempotent DRAFT submission record.

    Repeating the same (return_type, return_period) returns the existing record.
    """
    return_type = _parse_return_type(body.return_type)
    record = _governor.get_or_create(
        return_type=return_type,
        return_period=body.return_period,
        validated_by=body.validated_by,
        source_recon_id=body.source_recon_id,
    )
    return _to_response(record)


@router.post(
    "/gabriel/returns/{submission_id}/approve",
    response_model=SubmissionRecordResponse,
)
async def approve_gabriel_return(
    submission_id: str, body: ApproveRequest
) -> SubmissionRecordResponse:
    """HITL gate: approve a DRAFT and submit to FCA Gabriel.

    I-27: The ONLY endpoint that calls GabrielSubmissionPort.submit().
    Requires an explicit human decision (approved_by must identify the MLRO/CFO).
    Returns 422 if the record fails pre-submission validation.
    """
    try:
        submitted = _governor.approve(
            submission_id=submission_id,
            approved_by=body.approved_by,
            submission_port=_submission_port,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    logger.info(
        "Gabriel HITL approve: submission_id=%s by=%s ref=%s",
        submitted.submission_id,
        body.approved_by,
        submitted.submission_ref,
    )
    return _to_response(submitted)


@router.post(
    "/gabriel/returns/{submission_id}/reject",
    response_model=SubmissionRecordResponse,
)
async def reject_gabriel_return(
    submission_id: str, body: RejectRequest
) -> SubmissionRecordResponse:
    """HITL gate: reject a DRAFT submission record.

    Returns 404 if the record does not exist.
    """
    try:
        rejected = _governor.reject(
            submission_id=submission_id,
            rejected_by=body.rejected_by,
            reason=body.reason,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    logger.info(
        "Gabriel HITL reject: submission_id=%s by=%s",
        rejected.submission_id,
        body.rejected_by,
    )
    return _to_response(rejected)


@router.get(
    "/gabriel/deadline/{return_type}/{return_period}",
    response_model=DeadlineStatusResponse,
)
async def get_gabriel_deadline(
    return_type: str, return_period: str
) -> DeadlineStatusResponse:
    """Return the FCA Gabriel filing deadline for a given return type and period."""
    rt = _parse_return_type(return_type)
    try:
        ds = _governor.get_deadline_status(rt, return_period)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return DeadlineStatusResponse(
        return_type=ds.return_type.value,
        return_period=ds.return_period,
        deadline_date=ds.deadline_date,
        days_remaining=ds.days_remaining,
        is_overdue=ds.is_overdue,
    )
