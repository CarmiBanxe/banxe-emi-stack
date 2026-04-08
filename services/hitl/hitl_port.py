"""
services/hitl/hitl_port.py — Human-In-The-Loop domain types & port
IL-051 | Phase 2 #10 | banxe-emi-stack

HITL Review Queue: cases where FraudAMLPipeline returns decision=HOLD
are parked here for operator (CTIO / CEO) approval before rail submission.

FCA / regulatory basis:
  - I-04: EDD + HITL mandatory for ≥£10,000 (invariant, non-bypassable)
  - MLR 2017 Reg.28: EDD must be completed before proceeding
  - POCA 2002 s.330: SAR cases require MLRO review (4h SLA)
  - EU AI Act Art.14: meaningful human oversight of high-risk AI decisions
  - I-27: feedback_loop.py is SUPERVISED — it proposes, humans apply

SLA:
  - Standard HOLD (EDD/velocity/fraud HIGH): 24 hours
  - SAR cases: 4 hours (MLRO must review promptly, POCA 2002)
  - SANCTIONS: cases go directly to BLOCK in pipeline — never enter HITL queue

Operator privilege model (PRIVILEGE-MODEL.md):
  - OPERATOR role: approve / reject / escalate
  - MLRO role: required for ESCALATED cases
  - CEO: full access (congruent with MLRO for SAR decisions)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional, Protocol


# ── Enumerations ───────────────────────────────────────────────────────────────

class ReviewReason(str, Enum):
    """Why this case was held for human review."""
    FRAUD_HIGH = "FRAUD_HIGH"                  # Fraud score 70-84
    APP_SCAM = "APP_SCAM"                      # PSR APP 2024 scam indicator
    EDD_REQUIRED = "EDD_REQUIRED"              # MLR 2017 Reg.28 threshold
    VELOCITY_DAILY = "VELOCITY_DAILY"          # Daily velocity breach
    VELOCITY_MONTHLY = "VELOCITY_MONTHLY"      # Monthly velocity breach
    STRUCTURING = "STRUCTURING"                # POCA 2002 s.330
    SAR_REQUIRED = "SAR_REQUIRED"             # POCA 2002 — MLRO review
    AML_COMBINED = "AML_COMBINED"             # Multiple AML flags together


class CaseStatus(str, Enum):
    PENDING = "PENDING"         # Awaiting operator decision
    APPROVED = "APPROVED"       # Operator approved → payment proceeds
    REJECTED = "REJECTED"       # Operator rejected → payment blocked
    ESCALATED = "ESCALATED"     # Escalated to MLRO
    EXPIRED = "EXPIRED"         # SLA breached — auto-expired, MLRO alerted


class DecisionOutcome(str, Enum):
    APPROVE = "APPROVE"         # Human overrides HOLD → payment proceeds
    REJECT = "REJECT"           # Human confirms HOLD → payment rejected
    ESCALATE = "ESCALATE"       # → MLRO / senior compliance review


# SLA durations
_SLA_SAR_HOURS = 4       # POCA 2002 — MLRO must review SAR cases promptly
_SLA_STANDARD_HOURS = 24  # Standard EDD / velocity / fraud HIGH cases


# ── Domain types ───────────────────────────────────────────────────────────────

@dataclass
class ReviewCase:
    """
    A HOLD decision from FraudAMLPipeline awaiting human review.

    Lifecycle: PENDING → APPROVED | REJECTED | ESCALATED | EXPIRED
    Immutable fields (frozen after creation): case_id, transaction_id,
    customer_id, amount, currency, created_at, expires_at.
    """
    case_id: str
    transaction_id: str
    customer_id: str
    entity_type: str
    amount: Decimal
    currency: str
    reasons: list[ReviewReason]
    fraud_score: int
    fraud_risk: str              # LOW | MEDIUM | HIGH | CRITICAL
    aml_flags: list[str]         # active AML flag names
    hold_reasons: list[str]      # human-readable hold reasons from pipeline
    status: CaseStatus
    created_at: datetime
    expires_at: datetime

    # Mutable — set when operator decides
    assigned_to: Optional[str] = None
    decided_at: Optional[datetime] = None
    decision: Optional[DecisionOutcome] = None
    decision_by: Optional[str] = None
    decision_notes: str = ""

    @property
    def is_sar_case(self) -> bool:
        return ReviewReason.SAR_REQUIRED in self.reasons

    @property
    def is_expired(self) -> bool:
        return (
            self.status == CaseStatus.PENDING
            and datetime.now(timezone.utc) > self.expires_at
        )

    @property
    def hours_remaining(self) -> float:
        """Hours until SLA expiry. Negative if already expired."""
        delta = self.expires_at - datetime.now(timezone.utc)
        return delta.total_seconds() / 3600

    @classmethod
    def sla_hours(cls, reasons: list[ReviewReason]) -> int:
        """SLA in hours: 4h for SAR, 24h otherwise."""
        if ReviewReason.SAR_REQUIRED in reasons:
            return _SLA_SAR_HOURS
        return _SLA_STANDARD_HOURS


@dataclass
class HITLDecision:
    """
    A recorded human decision on a ReviewCase.
    Written to feedback corpus for supervised learning (I-27).
    Never applied autonomously — feedback_loop.py proposes, human applies.
    """
    case_id: str
    transaction_id: str
    customer_id: str
    amount: Decimal
    fraud_score: int
    reasons: list[str]
    outcome: DecisionOutcome
    decided_by: str
    decided_at: datetime
    notes: str

    def to_corpus_record(self) -> dict:
        """Serialise to JSON-compatible dict for feedback corpus."""
        return {
            "case_id": self.case_id,
            "transaction_id": self.transaction_id,
            "customer_id": self.customer_id,
            "amount": str(self.amount),
            "fraud_score": self.fraud_score,
            "reasons": self.reasons,
            "outcome": self.outcome.value,
            "decided_by": self.decided_by,
            "decided_at": self.decided_at.isoformat(),
            "notes": self.notes,
        }


@dataclass
class HITLStats:
    """Aggregated metrics over all cases. Used for Consumer Duty + FCA reporting."""
    total_cases: int
    pending_cases: int
    approved_cases: int
    rejected_cases: int
    escalated_cases: int
    expired_cases: int
    approval_rate: float           # approved / (approved + rejected) * 100
    avg_resolution_hours: float    # mean time from enqueue to decision
    oldest_pending_hours: float    # SLA pressure indicator


# ── Port ───────────────────────────────────────────────────────────────────────

class HITLPort(Protocol):
    """Hexagonal port for the HITL review queue."""

    def enqueue(
        self,
        transaction_id: str,
        customer_id: str,
        entity_type: str,
        amount: Decimal,
        currency: str,
        reasons: list[ReviewReason],
        fraud_score: int,
        fraud_risk: str,
        aml_flags: list[str],
        hold_reasons: list[str],
    ) -> ReviewCase: ...

    def get_case(self, case_id: str) -> Optional[ReviewCase]: ...

    def list_queue(
        self, status: Optional[CaseStatus] = None
    ) -> list[ReviewCase]: ...

    def decide(
        self,
        case_id: str,
        outcome: DecisionOutcome,
        decided_by: str,
        notes: str,
    ) -> ReviewCase: ...

    def stats(self) -> HITLStats: ...

    def get_feedback_corpus(self) -> list[dict]: ...
