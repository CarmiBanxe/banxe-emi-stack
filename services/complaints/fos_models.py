"""
services/complaints/fos_models.py
FOS Escalation models (IL-FOS-01).
Extends existing DISP complaints models.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class FOSCaseStatus(str, Enum):
    PREPARING = "PREPARING"
    READY = "READY"
    SUBMITTED = "SUBMITTED"
    RESOLVED = "RESOLVED"


class CustomerStatement(BaseModel):
    complaint_id: str
    customer_id: str
    summary: str
    desired_outcome: str
    model_config = {"frozen": True}


class FirmFinalResponse(BaseModel):
    complaint_id: str
    decision: str  # "upheld" / "not_upheld" / "partially_upheld"
    reasoning: str
    issued_at: str
    model_config = {"frozen": True}


class CaseTimeline(BaseModel):
    complaint_id: str
    events: list[dict]  # [{date, description}]
    weeks_elapsed: int
    model_config = {"frozen": True}


class FOSCasePackage(BaseModel):
    case_id: str
    complaint_id: str
    status: FOSCaseStatus
    timeline: CaseTimeline
    firm_final_response: FirmFinalResponse | None = None
    customer_statement: CustomerStatement | None = None
    prepared_at: str
    weeks_since_complaint: int
    model_config = {"frozen": True}


class FOSSubmissionResult(BaseModel):
    case_id: str
    submitted: bool
    reference_number: str | None = None
    submitted_at: str | None = None
    error: str | None = None
    model_config = {"frozen": True}
