"""
api/models/payments.py — Pydantic v2 schemas for Payment API
IL-046 | banxe-emi-stack

All monetary amounts are strings to preserve decimal precision (I-05).
Never use float for financial values.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from services.payment.payment_port import PaymentDirection, PaymentRail, PaymentStatus

# ── Request schemas ───────────────────────────────────────────────────────────


class BankAccountRequest(BaseModel):
    iban: str | None = None
    sort_code: str | None = None
    account_number: str | None = None
    bic: str | None = None
    holder_name: str


class InitiatePaymentRequest(BaseModel):
    rail: PaymentRail
    amount: str = Field(..., description="Decimal string, e.g. '100.00'. Never float.")
    currency: str = Field(..., min_length=3, max_length=3, description="ISO 4217")
    debtor_account: BankAccountRequest
    creditor_account: BankAccountRequest
    reference: str = Field(..., max_length=140)
    idempotency_key: str
    customer_id: str

    @field_validator("amount")
    @classmethod
    def validate_decimal_string(cls, v: str) -> str:
        import re

        if not re.match(r"^\d+(\.\d{1,2})?$", v):
            raise ValueError("amount must be a decimal string like '100.00'")
        if float(v) <= 0:
            raise ValueError("amount must be positive")
        return v

    @field_validator("currency")
    @classmethod
    def validate_currency_upper(cls, v: str) -> str:
        return v.upper()


# ── Response schemas ──────────────────────────────────────────────────────────


class PaymentResponse(BaseModel):
    payment_id: str
    provider_payment_id: str | None = None
    rail: PaymentRail
    status: PaymentStatus
    amount: str
    currency: str
    direction: PaymentDirection
    reference: str
    failure_reason: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
