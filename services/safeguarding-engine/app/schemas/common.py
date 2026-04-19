"""Common Pydantic schemas shared across Safeguarding Engine."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class CurrencyAmount(BaseModel):
    """Monetary amount with currency."""

    amount: Decimal = Field(..., decimal_places=2, description="Amount in minor units")
    currency: str = Field(default="GBP", max_length=3)


class DateRangeFilter(BaseModel):
    """Date range filter for queries."""

    start_date: Optional[date] = None
    end_date: Optional[date] = None


class StatusResponse(BaseModel):
    """Generic status response."""

    status: str
    message: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response wrapper."""

    items: List[T]
    total: int
    page: int = 1
    size: int = 50
    pages: int = 1


class AuditEventResponse(BaseModel):
    """Immutable audit event from ClickHouse."""

    event_id: uuid.UUID
    event_type: str
    entity_type: str
    entity_id: uuid.UUID
    action: str
    actor: str
    details: str
    position_date: Optional[date]
    amount: Optional[Decimal]
    timestamp: datetime


class AuditReportRequest(BaseModel):
    """Request for FCA-producible audit report."""

    start_date: date
    end_date: date
    event_type: Optional[str] = None
