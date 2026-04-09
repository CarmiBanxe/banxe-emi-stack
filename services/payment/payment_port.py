"""
payment_port.py — PaymentRailPort: hexagonal interface for payment rails
Block C-fps + C-sepa, IL-014
FCA PSR / PSD2 | banxe-emi-stack

OVERVIEW
--------
Defines the canonical domain types and the PaymentRailPort Protocol.

ALL payment rail adapters (Modulr, ClearBank, Mock) implement PaymentRailPort.
Business logic (PaymentService) depends ONLY on this interface — never on
a concrete provider SDK. This is the hexagonal / clean architecture boundary.

FCA requirements:
  - Payments must be idempotent (idempotency_key, CASS 7.15)
  - All amounts Decimal, never float (I-24)
  - Full audit trail per payment event (I-15, I-24)
  - GBP FPS: Faster Payments Service (UK domestic, near-instant)
  - EUR SEPA CT: SEPA Credit Transfer (EUR cross-border, D+1)
  - EUR SEPA Instant: SEPA Instant Credit Transfer (EUR, <10s, 24/7)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Protocol

# ── Enumerations ──────────────────────────────────────────────────────────────


class PaymentRail(str, Enum):
    """Supported payment rails."""

    FPS = "FPS"  # UK Faster Payments (GBP, near-instant)
    SEPA_CT = "SEPA_CT"  # SEPA Credit Transfer (EUR, D+1)
    SEPA_INSTANT = "SEPA_INSTANT"  # SEPA Instant Credit Transfer (EUR, <10s)
    BACS = "BACS"  # BACS Direct Credit (GBP, D+3, bulk)
    CHAPS = "CHAPS"  # CHAPS (GBP, same-day, high-value)


class PaymentStatus(str, Enum):
    """Lifecycle states of a payment."""

    PENDING = "PENDING"  # Submitted to rail, awaiting confirmation
    PROCESSING = "PROCESSING"  # Rail accepted, processing
    COMPLETED = "COMPLETED"  # Funds delivered, irrevocable
    FAILED = "FAILED"  # Rejected by rail (insufficient funds, invalid IBAN, etc.)
    RETURNED = "RETURNED"  # Completed but returned by beneficiary bank
    CANCELLED = "CANCELLED"  # Cancelled before processing


class PaymentDirection(str, Enum):
    OUTBOUND = "OUTBOUND"  # Banxe EMI → external account
    INBOUND = "INBOUND"  # External account → Banxe EMI


# ── Domain dataclasses ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BankAccount:
    """
    Beneficiary or debtor bank account.
    UK: sort_code + account_number required for FPS/BACS.
    EU: iban required for SEPA.
    bic is optional but recommended for SEPA CT.
    """

    account_holder_name: str
    iban: str | None = None
    bic: str | None = None
    sort_code: str | None = None  # UK: "20-20-15" or "202015"
    account_number: str | None = None  # UK: 8-digit account number
    bank_name: str | None = None
    country_code: str | None = None  # ISO-3166-1 alpha-2

    def is_uk_account(self) -> bool:
        return bool(self.sort_code and self.account_number)

    def is_eu_account(self) -> bool:
        return bool(self.iban)


@dataclass(frozen=True)
class PaymentIntent:
    """
    Instruction to initiate a payment.
    Constructed by PaymentService, submitted to PaymentRailPort.

    FCA note: idempotency_key MUST be stored and reused for retries.
    Sending the same idempotency_key twice must return the SAME result.
    """

    idempotency_key: str  # UUID4 — unique per payment attempt
    rail: PaymentRail
    direction: PaymentDirection
    amount: Decimal  # Major currency unit (e.g. £100.00) — NEVER float
    currency: str  # ISO-4217 (GBP, EUR)
    debtor_account: BankAccount  # Source account (Banxe safeguarding/operational)
    creditor_account: BankAccount  # Destination account
    reference: str  # Payment reference (max 18 chars for FPS)
    end_to_end_id: str  # ISO 20022 end-to-end identifier
    requested_at: datetime
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            raise TypeError(f"amount must be Decimal, got {type(self.amount).__name__} (FCA I-24)")
        if self.amount <= Decimal("0"):
            raise ValueError(f"amount must be positive, got {self.amount}")
        if self.currency not in ("GBP", "EUR"):
            raise ValueError(f"unsupported currency: {self.currency} (supported: GBP, EUR)")
        # Rail ↔ currency consistency checks
        if self.rail == PaymentRail.FPS and self.currency != "GBP":
            raise ValueError("FPS rail only supports GBP")
        if self.rail in (PaymentRail.SEPA_CT, PaymentRail.SEPA_INSTANT) and self.currency != "EUR":
            raise ValueError(f"{self.rail} rail only supports EUR")


@dataclass(frozen=True)
class PaymentResult:
    """
    Result returned by PaymentRailPort after submitting a payment.
    Contains the provider's reference for audit trail and status tracking.
    """

    idempotency_key: str  # Mirrors PaymentIntent.idempotency_key
    provider_payment_id: str  # Modulr / ClearBank payment ID
    status: PaymentStatus
    rail: PaymentRail
    amount: Decimal
    currency: str
    submitted_at: datetime
    error_code: str | None = None
    error_message: str | None = None
    estimated_settlement: datetime | None = None


@dataclass(frozen=True)
class PaymentStatusUpdate:
    """Webhook payload: status change notification from payment provider."""

    provider_payment_id: str
    idempotency_key: str | None
    new_status: PaymentStatus
    previous_status: PaymentStatus | None
    rail: PaymentRail
    amount: Decimal
    currency: str
    occurred_at: datetime
    raw_payload: dict = field(default_factory=dict)


# ── Port (interface) ──────────────────────────────────────────────────────────


class PaymentRailPort(Protocol):
    """
    Hexagonal port for payment rail providers.

    Implementations:
      - ModulrPaymentAdapter   — Modulr Finance (FCA EMI, FPS + SEPA)
      - MockPaymentAdapter     — In-memory mock for testing
      - ClearBankAdapter       — Future: ClearBank (post FCA authorisation)

    All amounts MUST be Decimal. All methods are synchronous.
    """

    def submit_payment(self, intent: PaymentIntent) -> PaymentResult:
        """
        Submit a payment to the rail.
        Must be idempotent: same idempotency_key → same result.
        """
        ...

    def get_payment_status(self, provider_payment_id: str) -> PaymentResult:
        """Fetch current status of a submitted payment."""
        ...

    def health_check(self) -> bool:
        """Return True if the provider API is reachable."""
        ...
