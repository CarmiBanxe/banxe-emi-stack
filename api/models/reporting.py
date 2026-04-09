"""
api/models/reporting.py — Pydantic v2 schemas for Compliance Reporting API
IL-052 | Phase 3 | banxe-emi-stack

Covers FIN060 (CASS 15.12.4R) and SAR (POCA 2002 s.330) endpoints.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, field_validator

from services.aml.sar_service import SARReason, SARStatus

# ── FIN060 ────────────────────────────────────────────────────────────────────


class FIN060GenerateRequest(BaseModel):
    """Generate FIN060 PDF for a reporting period."""

    period_start: date
    period_end: date
    avg_daily_client_funds: str  # Decimal string (I-05)
    peak_client_funds: str

    @field_validator("period_end")
    @classmethod
    def end_after_start(cls, v: date, info) -> date:
        start = info.data.get("period_start")
        if start and v < start:
            raise ValueError("period_end must be after period_start")
        return v


class FIN060Response(BaseModel):
    period_start: date
    period_end: date
    avg_daily_client_funds: Decimal
    peak_client_funds: Decimal
    frn: str
    status: str
    submission_id: str | None
    submitted_at: datetime | None
    deadline: date
    is_overdue: bool
    pdf_path: str | None
    errors: list[str]


# ── SAR ───────────────────────────────────────────────────────────────────────


class FileSARRequest(BaseModel):
    """Create a draft SAR for MLRO review."""

    transaction_id: str
    customer_id: str
    entity_type: str = "INDIVIDUAL"
    amount: str  # Decimal string (I-05)
    currency: str = "GBP"
    sar_reasons: list[SARReason]
    aml_flags: list[str] = []
    fraud_score: int = 0
    created_by: str = "system"

    @field_validator("sar_reasons")
    @classmethod
    def at_least_one_reason(cls, v: list) -> list:
        if not v:
            raise ValueError("At least one SAR reason required")
        return v


class MLRODecisionRequest(BaseModel):
    """MLRO approval or withdrawal of a SAR."""

    mlro_id: str
    notes: str = ""

    @field_validator("mlro_id")
    @classmethod
    def mlro_required(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("mlro_id must not be empty")
        return v.strip()


class WithdrawSARRequest(BaseModel):
    """MLRO withdrawal of a SAR with mandatory reason."""

    mlro_id: str
    reason: str

    @field_validator("reason")
    @classmethod
    def reason_required(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("reason is required for SAR withdrawal (JMLSG §6.7)")
        return v.strip()


class SARResponse(BaseModel):
    sar_id: str
    transaction_id: str
    customer_id: str
    entity_type: str
    amount: Decimal
    currency: str
    sar_reasons: list[str]
    aml_flags: list[str]
    fraud_score: int
    status: SARStatus
    created_at: datetime
    created_by: str
    mlro_reviewed_by: str | None
    mlro_reviewed_at: datetime | None
    mlro_notes: str
    submitted_at: datetime | None
    nca_reference: str | None
    errors: list[str]
    is_submittable: bool
    requires_mlro_action: bool

    model_config = {"from_attributes": True}


class SARListResponse(BaseModel):
    sars: list[SARResponse]
    total: int


class SARStatsResponse(BaseModel):
    total: int
    draft: int
    mlro_approved: int
    submitted: int
    submission_failed: int
    withdrawn: int
    submission_rate: float
