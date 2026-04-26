"""
services/complaints/complaints_models.py
Pydantic models for FCA DISP complaints (IL-DSP-01).
I-01: redress amounts as Decimal strings.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, field_validator


class ComplaintStatus(str, Enum):
    REGISTERED = "REGISTERED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    INVESTIGATING = "INVESTIGATING"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"
    ESCALATED = "ESCALATED"


class ComplaintCategory(str, Enum):
    SERVICE_QUALITY = "service_quality"
    FEES_CHARGES = "fees_charges"
    FRAUD_SCAM = "fraud_scam"
    PAYMENT_DELAY = "payment_delay"
    ACCOUNT_ACCESS = "account_access"
    DATA_PRIVACY = "data_privacy"


class Complaint(BaseModel):
    complaint_id: str
    customer_id: str
    category: ComplaintCategory
    description: str
    status: ComplaintStatus = ComplaintStatus.REGISTERED
    registered_at: str
    sla_days: int  # 15 simple, 35 complex, 56 final
    model_config = {"frozen": True}


class InvestigationReport(BaseModel):
    complaint_id: str
    investigator: str
    findings: str
    recommended_outcome: str
    investigated_at: str
    model_config = {"frozen": True}


class Resolution(BaseModel):
    complaint_id: str
    outcome: str  # "upheld", "partially_upheld", "not_upheld"
    redress_amount: str  # Decimal as string (I-01)
    resolved_at: str
    model_config = {"frozen": True}

    @field_validator("redress_amount")
    @classmethod
    def validate_redress(cls, v: str) -> str:
        d = Decimal(v)
        if d < Decimal("0"):
            raise ValueError("Redress amount must be non-negative (I-01)")
        return v


class FOSEscalation(BaseModel):
    complaint_id: str
    reason: str
    escalated_at: str
    model_config = {"frozen": True}
