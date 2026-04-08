"""
api/routers/consumer_duty.py — Consumer Duty endpoints
IL-050 | S9-06 | FCA PS22/9 | banxe-emi-stack

POST /v1/consumer-duty/vulnerability           — assess customer vulnerability (FG21/1)
GET  /v1/consumer-duty/vulnerability/{cust_id} — retrieve vulnerability assessment
POST /v1/consumer-duty/fair-value              — fair value assessment (COBS 6.1A)
POST /v1/consumer-duty/outcomes                — record outcome observation (PS22/9)
POST /v1/consumer-duty/report                  — generate board report (PS22/9 §10)
"""
from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, HTTPException

from api.models.consumer_duty import (
    ConsumerDutyReportResponse,
    FairValueAssessResponse,
    GenerateReportRequest,
    OutcomeRecordResponse,
    RecordOutcomeRequest,
    VulnerabilityAssessRequest,
    VulnerabilityAssessResponse,
    VulnerabilityGetResponse,
)
from services.consumer_duty.consumer_duty_service import ConsumerDutyService

router = APIRouter(tags=["Consumer Duty"])


@lru_cache(maxsize=1)
def _get_consumer_duty_service() -> ConsumerDutyService:
    return ConsumerDutyService()


# ── Vulnerability ──────────────────────────────────────────────────────────────

@router.post(
    "/consumer-duty/vulnerability",
    response_model=VulnerabilityAssessResponse,
    status_code=201,
    summary="Assess customer vulnerability (FCA FG21/1)",
)
def assess_vulnerability(
    body: VulnerabilityAssessRequest,
) -> VulnerabilityAssessResponse:
    """
    Classify customer vulnerability and trigger support actions.
    FCA FG21/1: firms must take practical action, not just record flags.
    """
    svc = _get_consumer_duty_service()
    result = svc.assess_vulnerability(
        customer_id=body.customer_id,
        flags=body.flags,
        assessed_by=body.assessed_by,
        notes=body.notes,
    )
    return VulnerabilityAssessResponse(
        customer_id=result.customer_id,
        flags=[f.value for f in result.flags],
        categories=[c.value for c in result.categories],
        support_actions=result.support_actions,
        is_vulnerable=result.is_vulnerable,
        assessed_at=result.assessed_at,
        assessed_by=result.assessed_by,
        notes=result.notes,
    )


@router.get(
    "/consumer-duty/vulnerability/{customer_id}",
    response_model=VulnerabilityGetResponse,
    summary="Get customer vulnerability assessment",
)
def get_vulnerability(customer_id: str) -> VulnerabilityGetResponse:
    """Retrieve the latest vulnerability assessment for a customer."""
    svc = _get_consumer_duty_service()
    assessment = svc.get_vulnerability(customer_id)
    if assessment is None:
        return VulnerabilityGetResponse(
            customer_id=customer_id,
            assessment=None,
            has_assessment=False,
        )
    return VulnerabilityGetResponse(
        customer_id=customer_id,
        has_assessment=True,
        assessment=VulnerabilityAssessResponse(
            customer_id=assessment.customer_id,
            flags=[f.value for f in assessment.flags],
            categories=[c.value for c in assessment.categories],
            support_actions=assessment.support_actions,
            is_vulnerable=assessment.is_vulnerable,
            assessed_at=assessment.assessed_at,
            assessed_by=assessment.assessed_by,
            notes=assessment.notes,
        ),
    )


# ── Fair value ─────────────────────────────────────────────────────────────────

@router.post(
    "/consumer-duty/fair-value",
    response_model=FairValueAssessResponse,
    status_code=200,
    summary="Assess product fair value (COBS 6.1A)",
)
def assess_fair_value(
    product_id: str,
    entity_type: str = "INDIVIDUAL",
) -> FairValueAssessResponse:
    """
    Assess whether product fees represent fair value vs. UK EMI benchmarks.
    Results must be reviewed by the board at least annually (PS22/9 §6.6).
    """
    svc = _get_consumer_duty_service()
    try:
        result = svc.assess_fair_value(product_id, entity_type)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return FairValueAssessResponse(
        product_id=result.product_id,
        entity_type=result.entity_type,
        annual_fee_estimate=result.annual_fee_estimate,
        benchmark_annual_fee=result.benchmark_annual_fee,
        benefit_score=result.benefit_score,
        verdict=result.verdict,
        rationale=result.rationale,
        assessed_at=result.assessed_at,
    )


# ── Outcome recording ──────────────────────────────────────────────────────────

@router.post(
    "/consumer-duty/outcomes",
    response_model=OutcomeRecordResponse,
    status_code=201,
    summary="Record Consumer Duty outcome observation (PS22/9)",
)
def record_outcome(body: RecordOutcomeRequest) -> OutcomeRecordResponse:
    """
    Record a Consumer Duty outcome observation for a customer interaction.
    Used to populate the annual board monitoring report (PS22/9 §10).
    """
    svc = _get_consumer_duty_service()
    result = svc.record_outcome(
        customer_id=body.customer_id,
        outcome=body.outcome,
        rating=body.rating,
        interaction_type=body.interaction_type,
        notes=body.notes,
    )
    return OutcomeRecordResponse(
        record_id=result.record_id,
        customer_id=result.customer_id,
        outcome=result.outcome,
        rating=result.rating,
        interaction_type=result.interaction_type,
        notes=result.notes,
        recorded_at=result.recorded_at,
    )


# ── Board report ───────────────────────────────────────────────────────────────

@router.post(
    "/consumer-duty/report",
    response_model=ConsumerDutyReportResponse,
    status_code=200,
    summary="Generate Consumer Duty board report (PS22/9 §10)",
)
def generate_report(body: GenerateReportRequest) -> ConsumerDutyReportResponse:
    """
    Generate Consumer Duty monitoring report for FCA board review.
    PS22/9 §10.12: board must review at least annually.
    """
    svc = _get_consumer_duty_service()
    report = svc.generate_report(
        period_start=body.period_start,
        period_end=body.period_end,
        total_customers=body.total_customers,
        complaints_count=body.complaints_count,
        avg_complaint_resolution_days=body.avg_complaint_resolution_days,
    )
    return ConsumerDutyReportResponse(
        period_start=report.period_start,
        period_end=report.period_end,
        generated_at=report.generated_at,
        total_customers=report.total_customers,
        vulnerable_customers=report.vulnerable_customers,
        vulnerable_pct=report.vulnerable_pct,
        overall_good_outcome_pct=report.overall_good_outcome_pct,
        outcome_ratings=report.outcome_ratings,
        fair_value_assessments=[
            FairValueAssessResponse(
                product_id=fva.product_id,
                entity_type=fva.entity_type,
                annual_fee_estimate=fva.annual_fee_estimate,
                benchmark_annual_fee=fva.benchmark_annual_fee,
                benefit_score=fva.benefit_score,
                verdict=fva.verdict,
                rationale=fva.rationale,
                assessed_at=fva.assessed_at,
            )
            for fva in report.fair_value_assessments
        ],
        complaints_count=report.complaints_count,
        avg_complaint_resolution_days=report.avg_complaint_resolution_days,
    )
