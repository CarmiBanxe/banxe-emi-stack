"""
api/models/gabriel.py
K-gabriel API request/response models.

All amounts are string (DecimalString) per I-01.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SubmissionRecordResponse(BaseModel):
    submission_id: str
    return_type: str
    return_period: str
    fca_item_code: str
    prepared_at: str
    validated_by: str
    status: str
    idempotency_key: str
    submitted_at: str | None = None
    submission_ref: str | None = None
    source_recon_id: str | None = None


class DeadlineStatusResponse(BaseModel):
    return_type: str
    return_period: str
    deadline_date: str
    days_remaining: int
    is_overdue: bool


class CreateDraftRequest(BaseModel):
    return_type: str = Field(..., description="FIN060 | BREACH_REPORT")
    return_period: str = Field(..., description="ISO period: YYYY-MM or YYYY-MM-DD")
    validated_by: str = Field(default="SYSTEM")
    source_recon_id: str | None = None


class ApproveRequest(BaseModel):
    approved_by: str = Field(..., description="Identity of MLRO / CFO approving submission")


class RejectRequest(BaseModel):
    rejected_by: str = Field(..., description="Identity of MLRO / CFO rejecting submission")
    reason: str = Field(..., description="Reason for rejection")
