"""
api/models/hitl.py — Pydantic v2 schemas for HITL Review Queue API
IL-051 | Phase 2 #10 | banxe-emi-stack
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, field_validator

from services.hitl.hitl_port import CaseStatus, DecisionOutcome, ReviewReason

# ── Request schemas ───────────────────────────────────────────────────────────


class EnqueueCaseRequest(BaseModel):
    """Manually enqueue a HOLD case (used when calling outside pipeline)."""

    transaction_id: str
    customer_id: str
    entity_type: str = "INDIVIDUAL"
    amount: str  # Decimal string (I-05)
    currency: str = "GBP"
    reasons: list[ReviewReason]
    fraud_score: int
    fraud_risk: str
    aml_flags: list[str] = []
    hold_reasons: list[str] = []

    @field_validator("fraud_score")
    @classmethod
    def validate_score(cls, v: int) -> int:
        if not 0 <= v <= 100:
            raise ValueError("fraud_score must be 0-100")
        return v


class DecideRequest(BaseModel):
    """Operator decision on a HOLD case."""

    outcome: DecisionOutcome
    decided_by: str  # operator_id
    notes: str = ""

    @field_validator("decided_by")
    @classmethod
    def validate_decided_by(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("decided_by must not be empty")
        return v.strip()


# ── Response schemas ──────────────────────────────────────────────────────────


class ReviewCaseResponse(BaseModel):
    case_id: str
    transaction_id: str
    customer_id: str
    entity_type: str
    amount: Decimal
    currency: str
    reasons: list[str]
    fraud_score: int
    fraud_risk: str
    aml_flags: list[str]
    hold_reasons: list[str]
    status: CaseStatus
    created_at: datetime
    expires_at: datetime
    hours_remaining: float
    is_sar_case: bool
    assigned_to: str | None
    decided_at: datetime | None
    decision: DecisionOutcome | None
    decision_by: str | None
    decision_notes: str

    model_config = {"from_attributes": True}


class QueueResponse(BaseModel):
    cases: list[ReviewCaseResponse]
    total: int
    pending: int
    sar_cases: int


class HITLStatsResponse(BaseModel):
    total_cases: int
    pending_cases: int
    approved_cases: int
    rejected_cases: int
    escalated_cases: int
    expired_cases: int
    approval_rate: float
    avg_resolution_hours: float
    oldest_pending_hours: float

    model_config = {"from_attributes": True}
