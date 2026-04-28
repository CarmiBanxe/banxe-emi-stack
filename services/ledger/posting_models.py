"""
services/ledger/posting_models.py
Models for payment-to-GL posting (IL-CBS-01).

Bridges payment lifecycle events to GL journal entries.
I-01: All monetary values are Decimal.
I-24: Immutable records.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum


class PaymentEventType(str, Enum):
    """Payment lifecycle events that trigger GL postings."""

    AUTHORIZED = "AUTHORIZED"
    CAPTURED = "CAPTURED"
    SETTLED = "SETTLED"
    REFUNDED = "REFUNDED"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"
    CHARGEBACK = "CHARGEBACK"
    FAILED = "FAILED"


@dataclass(frozen=True)
class PaymentEvent:
    """A payment lifecycle event to be posted to the GL (I-24 immutable)."""

    event_id: str
    transaction_id: str
    event_type: PaymentEventType
    amount: Decimal  # I-01
    currency: str
    customer_id: str
    beneficiary_jurisdiction: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            raise TypeError(f"amount must be Decimal, got {type(self.amount).__name__} (I-01)")
        if self.amount <= Decimal("0"):
            raise ValueError(f"amount must be positive, got {self.amount}")


@dataclass(frozen=True)
class PostingRule:
    """Defines how a payment event maps to GL debit/credit postings."""

    event_type: PaymentEventType
    debit_account_type: str  # e.g. "CUSTOMER_FUNDS", "MERCHANT_RECEIVABLE"
    credit_account_type: str  # e.g. "SETTLEMENT", "CUSTOMER_FUNDS"
    description_template: str


# Default posting rules per event type.
DEFAULT_POSTING_RULES: dict[PaymentEventType, PostingRule] = {
    PaymentEventType.CAPTURED: PostingRule(
        event_type=PaymentEventType.CAPTURED,
        debit_account_type="CUSTOMER_FUNDS",
        credit_account_type="SETTLEMENT_PENDING",
        description_template="Payment capture: {transaction_id}",
    ),
    PaymentEventType.SETTLED: PostingRule(
        event_type=PaymentEventType.SETTLED,
        debit_account_type="SETTLEMENT_PENDING",
        credit_account_type="MERCHANT_PAYABLE",
        description_template="Payment settlement: {transaction_id}",
    ),
    PaymentEventType.REFUNDED: PostingRule(
        event_type=PaymentEventType.REFUNDED,
        debit_account_type="MERCHANT_PAYABLE",
        credit_account_type="CUSTOMER_FUNDS",
        description_template="Payment refund: {transaction_id}",
    ),
    PaymentEventType.PARTIALLY_REFUNDED: PostingRule(
        event_type=PaymentEventType.PARTIALLY_REFUNDED,
        debit_account_type="MERCHANT_PAYABLE",
        credit_account_type="CUSTOMER_FUNDS",
        description_template="Partial refund: {transaction_id}",
    ),
    PaymentEventType.CHARGEBACK: PostingRule(
        event_type=PaymentEventType.CHARGEBACK,
        debit_account_type="MERCHANT_PAYABLE",
        credit_account_type="CUSTOMER_FUNDS",
        description_template="Chargeback: {transaction_id}",
    ),
}
