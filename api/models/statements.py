"""
api/models/statements.py — Statement endpoint request/response models
FCA PS7/24 | CASS 15 | banxe-emi-stack
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, field_validator


class TransactionLineResponse(BaseModel):
    """Single transaction line in a statement — mobile-safe field set."""

    date: str  # ISO-8601 date string
    description: str
    reference: str
    debit: str | None  # Decimal string or null
    credit: str | None  # Decimal string or null
    balance_after: str  # Decimal string
    transaction_id: str


class StatementResponse(BaseModel):
    """
    Account statement JSON response.
    All monetary amounts are Decimal strings (I-05 — never float).
    FCA PS7/24: client statement on request.
    """

    statement_id: str
    customer_id: str
    account_id: str
    currency: str
    period_start: str  # ISO-8601
    period_end: str  # ISO-8601
    opening_balance: str
    closing_balance: str
    total_debits: str
    total_credits: str
    net_movement: str
    transaction_count: int
    transactions: list[TransactionLineResponse]
    generated_at: str  # ISO-8601 datetime UTC


class StatementQueryParams(BaseModel):
    """Validated query parameters for statement requests."""

    customer_id: str
    currency: str = "GBP"
    from_date: date
    to_date: date

    @field_validator("currency")
    @classmethod
    def currency_upper(cls, v: str) -> str:
        return v.upper()

    @field_validator("to_date")
    @classmethod
    def to_after_from(cls, v: date, info) -> date:
        if "from_date" in info.data and v < info.data["from_date"]:
            raise ValueError("to_date must be >= from_date")
        return v
