"""
services/consumer_duty/models_v2.py
Consumer Duty Outcome Monitoring — Domain Models (Phase 50)
IL-CDO-01 | Phase 50 | Sprint 35

FCA: PS22/9 Consumer Duty (Jul 2023), FCA PROD, FCA COBS 2.1, FCA PRIN 12
Trust Zone: AMBER

All amounts Decimal (I-01). Append-only stores (I-24). HITL for irreversible actions (I-27).
Frozen dataclasses for value objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

# ── Enums ─────────────────────────────────────────────────────────────────────


class OutcomeType(StrEnum):
    """FCA PS22/9 four outcome areas."""

    PRODUCTS_SERVICES = "PRODUCTS_SERVICES"
    PRICE_VALUE = "PRICE_VALUE"
    CONSUMER_UNDERSTANDING = "CONSUMER_UNDERSTANDING"
    CONSUMER_SUPPORT = "CONSUMER_SUPPORT"


class VulnerabilityFlag(StrEnum):
    """Customer vulnerability classification (FCA FG21/1)."""

    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class InterventionType(StrEnum):
    """Product governance intervention type (FCA PROD)."""

    MONITOR = "MONITOR"
    ALERT = "ALERT"
    RESTRICT = "RESTRICT"
    WITHDRAW = "WITHDRAW"


class AssessmentStatus(StrEnum):
    """Outcome assessment status."""

    PENDING = "PENDING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    ESCALATED = "ESCALATED"


# ── Frozen dataclasses (value objects) ───────────────────────────────────────


@dataclass(frozen=True)
class ConsumerProfile:
    """Customer consumer profile for duty assessment.

    Frozen value object. risk_score is Decimal (I-01).
    """

    customer_id: str
    vulnerability_flag: VulnerabilityFlag
    product_ids: tuple[str, ...]
    last_assessed_at: str
    risk_score: Decimal  # I-01


@dataclass(frozen=True)
class OutcomeAssessment:
    """PS22/9 outcome assessment record.

    Frozen value object. score is Decimal 0.0–1.0 (I-01).
    """

    assessment_id: str
    customer_id: str
    outcome_type: OutcomeType
    score: Decimal  # I-01: 0.0–1.0
    status: AssessmentStatus
    assessed_at: str
    evidence: str


@dataclass(frozen=True)
class ProductGovernanceRecord:
    """FCA PROD product governance assessment.

    Frozen value object. fair_value_score is Decimal (I-01).
    """

    record_id: str
    product_id: str
    product_name: str
    target_market: str
    fair_value_score: Decimal  # I-01
    last_review_at: str
    intervention_type: InterventionType


@dataclass(frozen=True)
class VulnerabilityAlert:
    """Vulnerability alert (append-only, I-24).

    Frozen value object.
    """

    alert_id: str
    customer_id: str
    vulnerability_flag: VulnerabilityFlag
    trigger: str
    created_at: str
    reviewed_by: str | None


# ── HITL Proposal (I-27) ──────────────────────────────────────────────────────


@dataclass
class HITLProposal:
    """HITL L4 escalation proposal for irreversible consumer duty operations.

    I-27: AI PROPOSES, human DECIDES.
    """

    action: str
    entity_id: str
    requires_approval_from: str
    reason: str
    autonomy_level: str = "L4"


# ── Protocols (Protocol DI) ───────────────────────────────────────────────────


class OutcomeStorePort(Protocol):
    """Protocol for outcome assessment persistence (append-only, I-24)."""

    def append(self, assessment: OutcomeAssessment) -> None: ...  # I-24

    def list_by_customer(self, customer_id: str) -> list[OutcomeAssessment]: ...

    def list_by_outcome_type(self, outcome_type: OutcomeType) -> list[OutcomeAssessment]: ...


class ProductGovernancePort(Protocol):
    """Protocol for product governance persistence (append-only, I-24)."""

    def append(self, record: ProductGovernanceRecord) -> None: ...  # I-24

    def get(self, product_id: str) -> ProductGovernanceRecord | None: ...

    def list_failing(self) -> list[ProductGovernanceRecord]: ...


class VulnerabilityAlertPort(Protocol):
    """Protocol for vulnerability alert persistence (append-only, I-24)."""

    def append(self, alert: VulnerabilityAlert) -> None: ...  # I-24

    def list_unreviewed(self) -> list[VulnerabilityAlert]: ...


# ── InMemory stubs ────────────────────────────────────────────────────────────


class InMemoryOutcomeStore:
    """In-memory outcome store (append-only, I-24)."""

    def __init__(self) -> None:
        """Initialise empty outcome store."""
        self._data: list[OutcomeAssessment] = []

    def append(self, assessment: OutcomeAssessment) -> None:
        """Append assessment (I-24 — no delete/update)."""
        self._data.append(assessment)

    def list_by_customer(self, customer_id: str) -> list[OutcomeAssessment]:
        """List all assessments for a customer."""
        return [a for a in self._data if a.customer_id == customer_id]

    def list_by_outcome_type(self, outcome_type: OutcomeType) -> list[OutcomeAssessment]:
        """List all assessments for an outcome type."""
        return [a for a in self._data if a.outcome_type == outcome_type]

    def list_all(self) -> list[OutcomeAssessment]:
        """Return all assessments."""
        return list(self._data)


class InMemoryProductGovernance:
    """In-memory product governance store (append-only, I-24)."""

    def __init__(self) -> None:
        """Initialise empty product governance store."""
        self._data: list[ProductGovernanceRecord] = []

    def append(self, record: ProductGovernanceRecord) -> None:
        """Append governance record (I-24 — no delete/update)."""
        self._data.append(record)

    def get(self, product_id: str) -> ProductGovernanceRecord | None:
        """Get latest record for a product (most recent append)."""
        matches = [r for r in self._data if r.product_id == product_id]
        return matches[-1] if matches else None

    def list_failing(self) -> list[ProductGovernanceRecord]:
        """List records with RESTRICT or WITHDRAW intervention."""
        return [
            r
            for r in self._data
            if r.intervention_type in (InterventionType.RESTRICT, InterventionType.WITHDRAW)
        ]

    def list_all(self) -> list[ProductGovernanceRecord]:
        """Return all records."""
        return list(self._data)


class InMemoryVulnerabilityAlertStore:
    """In-memory vulnerability alert store (append-only, I-24)."""

    def __init__(self) -> None:
        """Initialise empty alert store."""
        self._data: list[VulnerabilityAlert] = []

    def append(self, alert: VulnerabilityAlert) -> None:
        """Append alert (I-24 — no delete/update)."""
        self._data.append(alert)

    def list_unreviewed(self) -> list[VulnerabilityAlert]:
        """List alerts not yet reviewed."""
        return [a for a in self._data if a.reviewed_by is None]

    def list_all(self) -> list[VulnerabilityAlert]:
        """Return all alerts."""
        return list(self._data)
