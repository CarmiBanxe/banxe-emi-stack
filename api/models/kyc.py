"""
api/models/kyc.py — Pydantic v2 schemas for KYC Workflow API
IL-046 | banxe-emi-stack
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from services.kyc.kyc_port import KYCStatus, KYCType, RejectionReason

# ── Request schemas ───────────────────────────────────────────────────────────


class CreateKYCWorkflowRequest(BaseModel):
    customer_id: str
    kyc_type: KYCType
    entity_type: str  # INDIVIDUAL | CORPORATE
    operator_id: str | None = None


class SubmitDocumentsRequest(BaseModel):
    document_ids: list[str]


class ApproveEDDRequest(BaseModel):
    mlro_user_id: str


class RejectWorkflowRequest(BaseModel):
    reason: RejectionReason


# ── Response schemas ──────────────────────────────────────────────────────────


class KYCWorkflowResponse(BaseModel):
    workflow_id: str
    customer_id: str
    kyc_type: KYCType
    status: KYCStatus
    requires_human_review: bool
    rejection_reason: RejectionReason | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
