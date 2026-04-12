"""
services/transaction_monitor/models/transaction.py — Transaction Pydantic models
IL-RTM-01 | banxe-emi-stack

TransactionEvent: core entity for AML monitoring.
All monetary amounts use Decimal (I-01 invariant).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TransactionType(str, Enum):
    PAYMENT = "payment"
    TRANSFER = "transfer"
    WITHDRAWAL = "withdrawal"
    DEPOSIT = "deposit"
    CRYPTO_ONRAMP = "crypto_onramp"
    CRYPTO_OFFRAMP = "crypto_offramp"
    P2P = "p2p"
    MERCHANT = "merchant"


class TransactionEvent(BaseModel):
    """Parsed transaction event for AML risk scoring.

    All monetary values use Decimal (I-01).
    Jurisdiction codes are ISO 3166-1 alpha-2.
    """

    transaction_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    amount: Decimal = Field(..., description="Transaction amount — always Decimal (I-01)")
    currency: str = Field(default="GBP", description="ISO 4217 currency code")
    sender_id: str
    receiver_id: str | None = None
    transaction_type: TransactionType = TransactionType.PAYMENT
    sender_jurisdiction: str = Field(default="GB", description="ISO 3166-1 alpha-2")
    receiver_jurisdiction: str | None = None
    sender_risk_level: str = Field(
        default="standard",
        description="standard | enhanced | high",
    )
    channel: str = Field(default="api", description="api | mobile | web | branch")
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Enrichment fields (populated by feature extractor)
    customer_avg_amount: Decimal | None = Field(
        default=None,
        description="Customer's 90-day average transaction amount (Decimal, I-01)",
    )


class RawEventPayload(BaseModel):
    """Raw event from RabbitMQ/Redis stream before parsing."""

    event_type: str = "transaction"
    payload: dict[str, Any]
    source: str = "api"
    received_at: datetime = Field(default_factory=datetime.utcnow)
