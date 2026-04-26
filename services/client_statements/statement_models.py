"""
services/client_statements/statement_models.py
Client statement models (IL-CST-01).
I-01: all amounts as Decimal strings.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, field_validator


class StatementFormat(str, Enum):
    PDF = "pdf"
    CSV = "csv"
    JSON = "json"


class StatementEntry(BaseModel):
    entry_id: str
    date: str
    description: str
    amount: str  # Decimal as string (I-01), positive = credit, negative = debit
    running_balance: str  # Decimal as string (I-01)
    currency: str = "GBP"
    transaction_type: str = "transfer"

    @field_validator("amount", "running_balance")
    @classmethod
    def validate_decimal(cls, v: str) -> str:
        try:
            Decimal(v)
        except Exception as exc:
            raise ValueError(f"Value {v!r} is not a valid Decimal string (I-01)") from exc
        return v

    model_config = {"frozen": True}


class BalanceSummary(BaseModel):
    opening_balance: str  # Decimal string (I-01)
    closing_balance: str  # Decimal string (I-01)
    total_credits: str
    total_debits: str
    currency: str = "GBP"
    model_config = {"frozen": True}


class FXSummary(BaseModel):
    conversions_count: int
    total_converted: str  # Decimal string (I-01)
    currencies: list[str]
    model_config = {"frozen": True}


class FeeBreakdown(BaseModel):
    total_fees: str  # Decimal string (I-01)
    by_type: dict[str, str]  # fee_type -> Decimal string
    model_config = {"frozen": True}


class Statement(BaseModel):
    statement_id: str
    customer_id: str
    period_start: str
    period_end: str
    format: StatementFormat
    entries: list[StatementEntry]
    balance_summary: BalanceSummary
    fx_summary: FXSummary | None = None
    fee_breakdown: FeeBreakdown | None = None
    generated_at: str
    model_config = {"frozen": True}
