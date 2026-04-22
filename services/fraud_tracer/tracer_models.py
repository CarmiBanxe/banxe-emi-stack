"""
services/fraud_tracer/tracer_models.py
Pydantic models for Fraud Transaction Tracer (IL-TRC-01).
I-01: all scores and amounts are Decimal strings.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, field_validator


class TraceRequest(BaseModel):
    transaction_id: str
    customer_id: str
    amount: str  # Decimal as string (I-01)
    currency: str = "GBP"
    country: str = "GB"
    counterparty_country: str = "GB"

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: str) -> str:
        d = Decimal(v)
        if d < Decimal("0"):
            raise ValueError("Amount must be non-negative (I-01)")
        return v

    model_config = {"frozen": True}


class TraceResult(BaseModel):
    transaction_id: str
    customer_id: str
    score: str  # Decimal as string (I-01, 0.0 - 1.0)
    flags: list[str]
    latency_ms: int
    status: str  # "CLEAR", "REVIEW", "BLOCK"

    model_config = {"frozen": True}


class VelocityResult(BaseModel):
    customer_id: str
    window_minutes: int
    tx_count: int
    total_amount: str  # Decimal as string (I-01)
    breached: bool
    model_config = {"frozen": True}


class TracerConfig(BaseModel):
    max_tx_count: int = 10
    max_tx_amount: str = "50000.00"  # Decimal as string (I-01)
    score_threshold_review: str = "0.6"
    score_threshold_block: str = "0.8"
    model_config = {"frozen": True}
