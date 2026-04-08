"""
api/models/fraud.py — Pydantic v2 schemas for Fraud + AML Assessment API
IL-049 | S9-05 | banxe-emi-stack

POST /v1/fraud/assess — pre-payment fraud + AML gate
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator

_AMOUNT_RE = re.compile(r"^\d+(\.\d{1,2})?$")


class FraudAssessRequest(BaseModel):
    """
    Request to assess a transaction through Fraud + AML pipeline.
    All fields reflect the payment intent before rail submission.
    """
    transaction_id: str
    customer_id: str
    entity_type: str = "INDIVIDUAL"      # INDIVIDUAL | COMPANY
    amount: str                          # Decimal string — I-05 (no float)
    currency: str = "GBP"
    destination_account: str
    destination_sort_code: str = ""
    destination_country: str             # ISO-3166-1 alpha-2
    payment_rail: str = "FPS"            # FPS | SEPA_CT | SEPA_INSTANT | BACS
    device_id: Optional[str] = None
    customer_ip: Optional[str] = None
    session_id: Optional[str] = None
    first_transaction_to_payee: bool = True
    amount_unusual: bool = False
    is_pep: bool = False
    is_sanctions_hit: bool = False
    is_fx: bool = False

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: str) -> str:
        if not _AMOUNT_RE.match(v):
            raise ValueError(
                "amount must be a positive decimal string with up to 2 decimal places "
                "(e.g. '1000.00')"
            )
        return v

    @field_validator("entity_type")
    @classmethod
    def validate_entity_type(cls, v: str) -> str:
        if v not in ("INDIVIDUAL", "COMPANY"):
            raise ValueError("entity_type must be INDIVIDUAL or COMPANY")
        return v

    @field_validator("destination_country")
    @classmethod
    def validate_country(cls, v: str) -> str:
        if len(v) != 2 or not v.isalpha():
            raise ValueError("destination_country must be ISO-3166-1 alpha-2 (e.g. 'GB')")
        return v.upper()


class FraudAssessResponse(BaseModel):
    """
    Combined Fraud + AML decision for a transaction.
    Decision field drives payment flow:
      APPROVE → proceed to rail submission
      HOLD    → queue for HITL review (do NOT submit)
      BLOCK   → reject immediately (do NOT submit)
    """
    transaction_id: str
    customer_id: str
    decision: str                        # APPROVE | HOLD | BLOCK

    # Fraud findings
    fraud_risk: str                      # LOW | MEDIUM | HIGH | CRITICAL
    fraud_score: int
    app_scam_indicator: str
    fraud_factors: list[str]
    fraud_latency_ms: float

    # AML findings
    aml_edd_required: bool
    aml_velocity_daily_breach: bool
    aml_velocity_monthly_breach: bool
    aml_structuring_signal: bool
    aml_sar_required: bool
    aml_sanctions_block: bool
    aml_reasons: list[str]

    # Decision breakdown
    block_reasons: list[str]
    hold_reasons: list[str]
    requires_hitl: bool

    assessed_at: datetime

    model_config = {"from_attributes": True}
