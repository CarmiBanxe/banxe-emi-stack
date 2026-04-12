"""Pydantic schemas for breach management."""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


class BreachCreate(BaseModel):
    """Report a safeguarding breach."""
    breach_type: str = Field(..., description="shortfall|timing|recon_break|other")
    severity: str = Field(..., description="critical|major|minor")
    description: str
    shortfall_amount: Optional[Decimal] = None
    created_by: str = "system"


class BreachResponse(BaseModel):
    """Breach report details."""
    id: uuid.UUID
    breach_type: str
    severity: str
    description: str
    shortfall_amount: Optional[Decimal]
    detected_at: datetime
    fca_notified: bool
    fca_notified_at: Optional[datetime]
    resolved: bool
    resolved_at: Optional[datetime]
    remediation_notes: Optional[str]
    created_by: str


class BreachResolve(BaseModel):
    """Mark a breach as resolved."""
    remediation_notes: str
    resolved_by: str = "system"


class BreachListResponse(BaseModel):
    """List of breaches with summary."""
    breaches: List[BreachResponse]
    total: int
    active_count: int
    fca_notifications_pending: int
