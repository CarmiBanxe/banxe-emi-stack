"""
fraud_port.py — FraudScoringPort: hexagonal interface for fraud scoring
S5-22 (Real-time fraud scoring <100ms) | S5-26 (APP scam detection PSR APP 2024)
PSR APP 2024 | FCA CONC 13 | banxe-emi-stack

WHY THIS FILE EXISTS
--------------------
PSR APP 2024 (effective 7 Oct 2024) mandates that all UK EMIs implement
real-time detection for Authorised Push Payment (APP) scams. Sardine.ai
is the target provider. This Port defines the canonical interface so that:
  - FraudService and AML orchestrator depend ONLY on this interface
  - SardineFraudAdapter (live) and MockFraudAdapter (test/sandbox) are
    interchangeable at runtime via FRAUD_ADAPTER env var
  - No provider SDK leaks into business logic

Performance SLA: fraud score must be returned within 100ms (S5-22).
The mock adapter returns instantly; SardineFraudAdapter must enforce this
via timeout.

FCA rules referenced:
  - PSR 2024 APP scam reimbursement: mandatory detection layer
  - FCA CONC 13: responsible lending + fraud prevention
  - I-04 (≥£10,000 → EDD), I-06 (HARD_BLOCK → REJECT)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Protocol


class FraudRisk(str, Enum):
    """Fraud risk decision from scoring engine."""

    LOW = "LOW"  # score < 40 — proceed normally
    MEDIUM = "MEDIUM"  # score 40-69 — enhanced checks / HITL
    HIGH = "HIGH"  # score 70-84 — HOLD + MLRO review
    CRITICAL = "CRITICAL"  # score ≥ 85 — BLOCK + SAR consideration


class AppScamIndicator(str, Enum):
    """PSR APP 2024 scam pattern categories."""

    PURCHASE_SCAM = "PURCHASE_SCAM"
    ROMANCE_SCAM = "ROMANCE_SCAM"
    INVESTMENT_SCAM = "INVESTMENT_SCAM"
    IMPERSONATION_BANK = "IMPERSONATION_BANK"
    IMPERSONATION_POLICE = "IMPERSONATION_POLICE"
    IMPERSONATION_HMRC = "IMPERSONATION_HMRC"
    CEO_FRAUD = "CEO_FRAUD"
    INVOICE_REDIRECT = "INVOICE_REDIRECT"
    ADVANCE_FEE = "ADVANCE_FEE"
    NONE = "NONE"


@dataclass(frozen=True)
class FraudScoringRequest:
    """Input to fraud scoring engine."""

    transaction_id: str
    customer_id: str
    amount: Decimal
    currency: str
    destination_account: str  # IBAN or account number
    destination_sort_code: str  # UK sort code (or empty for SEPA)
    destination_country: str  # ISO-3166-1 alpha-2
    payment_rail: str  # FPS / SEPA_CT / SEPA_INSTANT / BACS
    customer_device_id: str | None = None
    customer_ip: str | None = None
    session_id: str | None = None
    first_transaction_to_payee: bool = True
    amount_unusual: bool = False  # significantly above customer average
    entity_type: str = "INDIVIDUAL"  # "INDIVIDUAL" | "COMPANY" — affects AML thresholds


@dataclass
class FraudScoringResult:
    """Output from fraud scoring engine."""

    transaction_id: str
    risk: FraudRisk
    score: int  # 0-100 composite
    app_scam_indicator: AppScamIndicator
    block: bool  # True → payment must be blocked
    hold_for_review: bool  # True → HITL required
    factors: list[str] = field(default_factory=list)  # human-readable reasons
    provider: str = "unknown"
    latency_ms: float = 0.0
    scored_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class FraudScoringPort(Protocol):
    """
    Hexagonal port for real-time fraud scoring.
    All adapters MUST return within 100ms (S5-22 SLA).
    """

    def score(self, request: FraudScoringRequest) -> FraudScoringResult: ...
    def health(self) -> bool: ...
