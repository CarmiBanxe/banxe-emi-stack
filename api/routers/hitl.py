"""
api/routers/hitl.py — HITL Review Queue endpoints
IL-051 | Phase 2 #10 | banxe-emi-stack

GET  /v1/hitl/queue              — list cases (filter by status)
POST /v1/hitl/queue              — enqueue a case manually
GET  /v1/hitl/queue/{case_id}    — get single case
POST /v1/hitl/queue/{case_id}/decide — operator decision
GET  /v1/hitl/stats              — queue metrics
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache

from fastapi import APIRouter, HTTPException

from api.models.hitl import (
    DecideRequest,
    EnqueueCaseRequest,
    HITLStatsResponse,
    QueueResponse,
    ReviewCaseResponse,
)
from services.hitl.hitl_port import CaseStatus
from services.hitl.hitl_service import HITLCaseError, HITLService

router = APIRouter(tags=["HITL Review Queue"])


@lru_cache(maxsize=1)
def _get_hitl_service() -> HITLService:
    return HITLService()


def _case_to_response(case) -> ReviewCaseResponse:  # type: ignore[no-untyped-def]
    return ReviewCaseResponse(
        case_id=case.case_id,
        transaction_id=case.transaction_id,
        customer_id=case.customer_id,
        entity_type=case.entity_type,
        amount=case.amount,
        currency=case.currency,
        reasons=[r.value for r in case.reasons],
        fraud_score=case.fraud_score,
        fraud_risk=case.fraud_risk,
        aml_flags=case.aml_flags,
        hold_reasons=case.hold_reasons,
        status=case.status,
        created_at=case.created_at,
        expires_at=case.expires_at,
        hours_remaining=round(case.hours_remaining, 2),
        is_sar_case=case.is_sar_case,
        assigned_to=case.assigned_to,
        decided_at=case.decided_at,
        decision=case.decision,
        decision_by=case.decision_by,
        decision_notes=case.decision_notes,
    )


@router.get(
    "/hitl/queue",
    response_model=QueueResponse,
    summary="List HITL review queue",
)
def list_queue(
    status: CaseStatus | None = None,
) -> QueueResponse:
    """
    List HITL review cases. Filter by status (PENDING / APPROVED / REJECTED /
    ESCALATED / EXPIRED). Omit status to return all cases.
    SAR cases are sorted first (4h SLA).
    """
    svc = _get_hitl_service()
    cases = svc.list_queue(status=status)
    pending = sum(1 for c in cases if c.status == CaseStatus.PENDING)
    sar = sum(1 for c in cases if c.is_sar_case)
    return QueueResponse(
        cases=[_case_to_response(c) for c in cases],
        total=len(cases),
        pending=pending,
        sar_cases=sar,
    )


@router.post(
    "/hitl/queue",
    response_model=ReviewCaseResponse,
    status_code=201,
    summary="Enqueue a HITL review case",
)
def enqueue_case(body: EnqueueCaseRequest) -> ReviewCaseResponse:
    """
    Manually enqueue a transaction for HITL review.
    Normally called automatically by the payment service when
    FraudAMLPipeline returns decision=HOLD. Available for direct use.
    """
    svc = _get_hitl_service()
    case = svc.enqueue(
        transaction_id=body.transaction_id,
        customer_id=body.customer_id,
        entity_type=body.entity_type,
        amount=Decimal(body.amount),
        currency=body.currency,
        reasons=body.reasons,
        fraud_score=body.fraud_score,
        fraud_risk=body.fraud_risk,
        aml_flags=body.aml_flags,
        hold_reasons=body.hold_reasons,
    )
    return _case_to_response(case)


@router.get(
    "/hitl/queue/{case_id}",
    response_model=ReviewCaseResponse,
    summary="Get HITL case by ID",
)
def get_case(case_id: str) -> ReviewCaseResponse:
    svc = _get_hitl_service()
    case = svc.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    return _case_to_response(case)


@router.post(
    "/hitl/queue/{case_id}/decide",
    response_model=ReviewCaseResponse,
    summary="Record operator decision on a HITL case",
)
def decide_case(case_id: str, body: DecideRequest) -> ReviewCaseResponse:
    """
    Record a human decision: APPROVE / REJECT / ESCALATE.

    APPROVE: payment proceeds to rail submission.
    REJECT:  payment is rejected — customer notified.
    ESCALATE: case forwarded to MLRO for senior review.

    Decision is written to feedback corpus (I-27: supervised feedback loop).
    """
    svc = _get_hitl_service()
    try:
        case = svc.decide(
            case_id=case_id,
            outcome=body.outcome,
            decided_by=body.decided_by,
            notes=body.notes,
        )
    except HITLCaseError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _case_to_response(case)


@router.get(
    "/hitl/stats",
    response_model=HITLStatsResponse,
    summary="HITL queue metrics",
)
def get_stats() -> HITLStatsResponse:
    """
    Queue performance metrics: pending count, approval rate,
    avg resolution time, oldest pending case (SLA pressure).
    Used for FCA Consumer Duty monitoring (EU AI Act Art.14).
    """
    svc = _get_hitl_service()
    s = svc.stats()
    return HITLStatsResponse(
        total_cases=s.total_cases,
        pending_cases=s.pending_cases,
        approved_cases=s.approved_cases,
        rejected_cases=s.rejected_cases,
        escalated_cases=s.escalated_cases,
        expired_cases=s.expired_cases,
        approval_rate=s.approval_rate,
        avg_resolution_hours=s.avg_resolution_hours,
        oldest_pending_hours=s.oldest_pending_hours,
    )
