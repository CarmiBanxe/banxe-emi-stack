"""
api/models/consumer_duty.py — Pydantic v2 schemas for Consumer Duty API
IL-050 | S9-06 | FCA PS22/9 | banxe-emi-stack
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, field_validator

from services.consumer_duty.consumer_duty_port import (
    ConsumerDutyOutcome,
    FairValueVerdict,
    OutcomeRating,
    VulnerabilityFlag,
)

# ── Request schemas ───────────────────────────────────────────────────────────


class VulnerabilityAssessRequest(BaseModel):
    """Flag a customer's vulnerability and trigger support actions."""

    customer_id: str
    flags: list[VulnerabilityFlag]
    assessed_by: str = "system"
    notes: str = ""


class RecordOutcomeRequest(BaseModel):
    """Record a Consumer Duty outcome observation for a customer interaction."""

    customer_id: str
    outcome: ConsumerDutyOutcome
    rating: OutcomeRating
    interaction_type: str  # PAYMENT | KYC | COMPLAINT | SUPPORT | ONBOARDING
    notes: str = ""

    @field_validator("interaction_type")
    @classmethod
    def validate_interaction_type(cls, v: str) -> str:
        valid = {"PAYMENT", "KYC", "COMPLAINT", "SUPPORT", "ONBOARDING"}
        if v.upper() not in valid:
            raise ValueError(f"interaction_type must be one of {sorted(valid)}")
        return v.upper()


class GenerateReportRequest(BaseModel):
    """Parameters for Consumer Duty board report generation."""

    period_start: date
    period_end: date
    total_customers: int
    complaints_count: int = 0
    avg_complaint_resolution_days: float = 0.0

    @field_validator("period_end")
    @classmethod
    def validate_period(cls, v: date, info) -> date:
        start = info.data.get("period_start")
        if start and v < start:
            raise ValueError("period_end must be after period_start")
        return v


# ── Response schemas ──────────────────────────────────────────────────────────


class VulnerabilityAssessResponse(BaseModel):
    customer_id: str
    flags: list[str]
    categories: list[str]
    support_actions: list[str]
    is_vulnerable: bool
    assessed_at: datetime
    assessed_by: str
    notes: str

    model_config = {"from_attributes": True}


class FairValueAssessResponse(BaseModel):
    product_id: str
    entity_type: str
    annual_fee_estimate: Decimal
    benchmark_annual_fee: Decimal
    benefit_score: int
    verdict: FairValueVerdict
    rationale: str
    assessed_at: datetime

    model_config = {"from_attributes": True}


class OutcomeRecordResponse(BaseModel):
    record_id: str
    customer_id: str
    outcome: ConsumerDutyOutcome
    rating: OutcomeRating
    interaction_type: str
    notes: str
    recorded_at: datetime

    model_config = {"from_attributes": True}


class OutcomeRatingMatrix(BaseModel):
    """Outcome ratings per consumer duty area."""

    products_and_services: dict[str, int]
    price_and_value: dict[str, int]
    consumer_understanding: dict[str, int]
    consumer_support: dict[str, int]


class ConsumerDutyReportResponse(BaseModel):
    period_start: date
    period_end: date
    generated_at: datetime
    total_customers: int
    vulnerable_customers: int
    vulnerable_pct: float
    overall_good_outcome_pct: float
    outcome_ratings: dict[str, dict[str, int]]
    fair_value_assessments: list[FairValueAssessResponse]
    complaints_count: int
    avg_complaint_resolution_days: float

    model_config = {"from_attributes": True}


class VulnerabilityGetResponse(BaseModel):
    """Response for GET /v1/consumer-duty/vulnerability/{customer_id}"""

    customer_id: str
    assessment: VulnerabilityAssessResponse | None
    has_assessment: bool
