"""Pydantic schemas for safeguarding core operations."""
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


# --- Safeguarding Request ---
class SafeguardingRequest(BaseModel):
    """Record a new safeguarding obligation."""
    client_fund_amount: Decimal
    currency: str = "GBP"
    source: str = "e-money-receipt"
    reference: Optional[str] = None
    transaction_id: Optional[uuid.UUID] = None


class SafeguardingResponse(BaseModel):
    """Safeguarding obligation recorded."""
    id: uuid.UUID
    client_fund_amount: Decimal
    currency: str
    source: str
    safeguarded: bool = False
    safeguarded_at: Optional[datetime] = None
    created_at: datetime


# --- Position ---
class PositionDetailResponse(BaseModel):
    """Single account balance in a position."""
    account_id: uuid.UUID
    bank_name: str
    balance: Decimal
    balance_source: str
    recorded_at: datetime


class PositionResponse(BaseModel):
    """Daily safeguarding position summary."""
    id: uuid.UUID
    position_date: date
    total_client_funds: Decimal
    total_safeguarded: Decimal
    shortfall: Decimal
    is_compliant: bool
    calculated_at: datetime
    details: List[PositionDetailResponse] = []


class ShortfallResponse(BaseModel):
    """Shortfall calculation result."""
    position_date: date
    total_client_funds: Decimal
    total_safeguarded: Decimal
    shortfall: Decimal
    is_compliant: bool
    breach_triggered: bool = False


# --- Accounts ---
class AccountCreate(BaseModel):
    """Create a safeguarding bank account."""
    bank_name: str = Field(..., max_length=255)
    account_number: str = Field(..., max_length=50)
    sort_code: Optional[str] = Field(None, max_length=10)
    iban: Optional[str] = Field(None, max_length=34)
    currency: str = Field(default="GBP", max_length=3)
    account_type: str = Field(default="segregated", max_length=20)


class AccountUpdate(BaseModel):
    """Update safeguarding account metadata."""
    bank_name: Optional[str] = None
    status: Optional[str] = None
    acknowledgement_letter_received: Optional[bool] = None
    acknowledgement_date: Optional[datetime] = None


class AccountResponse(BaseModel):
    """Safeguarding account details."""
    id: uuid.UUID
    bank_name: str
    account_number: str
    sort_code: Optional[str]
    iban: Optional[str]
    currency: str
    account_type: str
    status: str
    acknowledgement_letter_received: bool
    acknowledgement_date: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class BalanceSnapshotCreate(BaseModel):
    """Record a balance snapshot from bank."""
    balance: Decimal
    balance_source: str = Field(default="bank_api", description="bank_api|manual|statement")
    recorded_at: Optional[datetime] = None
