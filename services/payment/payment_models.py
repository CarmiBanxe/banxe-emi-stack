"""
services/payment/payment_models.py
Payment transaction lifecycle models (IL-PAY-02).

Full payment lifecycle: PENDING → AUTHORIZED → CAPTURED → SETTLED → REFUNDED/FAILED
Covers S4-01 (initiation), S4-02 (auth), S4-03 (settlement), S4-05 (refund).

I-01: All monetary values are Decimal — never float.
I-02: Blocked jurisdictions enforced via JurisdictionBlockedError.
I-24: Immutable audit trail via frozen dataclasses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum


class TransactionStatus(str, Enum):
    """Full payment lifecycle states."""

    PENDING = "PENDING"
    AUTHORIZED = "AUTHORIZED"
    CAPTURED = "CAPTURED"
    SETTLED = "SETTLED"
    REFUNDED = "REFUNDED"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    CHARGEBACK = "CHARGEBACK"


# Valid transitions for the payment state machine.
VALID_TRANSITIONS: dict[TransactionStatus, frozenset[TransactionStatus]] = {
    TransactionStatus.PENDING: frozenset(
        {
            TransactionStatus.AUTHORIZED,
            TransactionStatus.FAILED,
            TransactionStatus.CANCELLED,
        }
    ),
    TransactionStatus.AUTHORIZED: frozenset(
        {
            TransactionStatus.CAPTURED,
            TransactionStatus.CANCELLED,
            TransactionStatus.FAILED,
        }
    ),
    TransactionStatus.CAPTURED: frozenset(
        {
            TransactionStatus.SETTLED,
            TransactionStatus.FAILED,
        }
    ),
    TransactionStatus.SETTLED: frozenset(
        {
            TransactionStatus.REFUNDED,
            TransactionStatus.PARTIALLY_REFUNDED,
            TransactionStatus.CHARGEBACK,
        }
    ),
    TransactionStatus.PARTIALLY_REFUNDED: frozenset(
        {
            TransactionStatus.REFUNDED,
            TransactionStatus.PARTIALLY_REFUNDED,
            TransactionStatus.CHARGEBACK,
        }
    ),
    TransactionStatus.REFUNDED: frozenset(),
    TransactionStatus.FAILED: frozenset(),
    TransactionStatus.CANCELLED: frozenset(),
    TransactionStatus.CHARGEBACK: frozenset(),
}

SUPPORTED_CURRENCIES: frozenset[str] = frozenset({"GBP", "EUR", "USD"})


@dataclass(frozen=True)
class PaymentTransaction:
    """Immutable snapshot of a payment at a point in its lifecycle (I-24)."""

    transaction_id: str
    idempotency_key: str
    customer_id: str
    amount: Decimal  # I-01: Decimal ONLY
    currency: str
    beneficiary_jurisdiction: str
    status: TransactionStatus
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    reference: str = ""
    refunded_amount: Decimal = Decimal("0")  # I-01: Decimal ONLY
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            raise TypeError(f"amount must be Decimal, got {type(self.amount).__name__} (I-01)")
        if not isinstance(self.refunded_amount, Decimal):
            raise TypeError(
                f"refunded_amount must be Decimal, got {type(self.refunded_amount).__name__} (I-01)"
            )
        if self.amount <= Decimal("0"):
            raise ValueError(f"amount must be positive, got {self.amount}")
        if self.currency not in SUPPORTED_CURRENCIES:
            raise ValueError(
                f"unsupported currency: {self.currency} (supported: {', '.join(sorted(SUPPORTED_CURRENCIES))})"
            )


@dataclass(frozen=True)
class AuditEntry:
    """Immutable audit record for payment lifecycle events (I-24)."""

    transaction_id: str
    action: str
    old_status: TransactionStatus | None
    new_status: TransactionStatus
    amount: Decimal  # I-01
    currency: str
    actor: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    details: str = ""
