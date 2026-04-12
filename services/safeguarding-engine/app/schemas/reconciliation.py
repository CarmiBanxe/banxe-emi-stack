"""Pydantic schemas for reconciliation operations."""
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


class DailyReconRequest(BaseModel):
    """Trigger daily internal reconciliation."""
    recon_date: Optional[date] = None  # defaults to today
    force: bool = False  # re-run even if already done


class MonthlyReconRequest(BaseModel):
    """Trigger monthly external reconciliation."""
    month: int = Field(..., ge=1, le=12)
    year: int = Field(..., ge=2020)
    bank_statement_ids: List[uuid.UUID] = []


class BreakItem(BaseModel):
    """Single reconciliation break item."""
    description: str
    expected: Decimal
    actual: Decimal
    difference: Decimal
    category: str  # timing, amount, missing


class ReconciliationResponse(BaseModel):
    """Reconciliation result summary."""
    id: uuid.UUID
    recon_type: str  # daily, monthly
    recon_date: date
    ledger_total: Decimal
    bank_total: Decimal
    difference: Decimal
    status: str  # matched, break, pending
    break_count: int = 0
    created_at: datetime


class ReconciliationDetailResponse(BaseModel):
    """Detailed reconciliation report with break items."""
    id: uuid.UUID
    recon_type: str
    recon_date: date
    ledger_total: Decimal
    bank_total: Decimal
    difference: Decimal
    status: str
    break_items: List[BreakItem] = []
    resolved_at: Optional[datetime] = None
    created_at: datetime
