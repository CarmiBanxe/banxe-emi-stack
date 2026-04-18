"""
services/risk_management/models.py
IL-RMS-01 | Phase 37 | banxe-emi-stack

Domain models, protocols, and in-memory stubs for Risk Management & Scoring Engine.
Protocol DI: Port (Protocol) → InMemory stub (tests) → Real adapter (production)
I-01: All scores as Decimal (never float).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Protocol
import uuid

# ── Enums ────────────────────────────────────────────────────────────────────


class RiskCategory(str, Enum):
    CREDIT = "CREDIT"
    OPERATIONAL = "OPERATIONAL"
    AML = "AML"
    FRAUD = "FRAUD"
    MARKET = "MARKET"
    LIQUIDITY = "LIQUIDITY"
    REPUTATIONAL = "REPUTATIONAL"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ScoreModel(str, Enum):
    WEIGHTED_AVERAGE = "WEIGHTED_AVERAGE"
    MONTE_CARLO = "MONTE_CARLO"
    LOGISTIC_REGRESSION = "LOGISTIC_REGRESSION"
    RULE_BASED = "RULE_BASED"


class AssessmentStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    OVERDUE = "OVERDUE"
    ESCALATED = "ESCALATED"


class MitigationAction(str, Enum):
    IDENTIFIED = "IDENTIFIED"
    IN_PROGRESS = "IN_PROGRESS"
    MITIGATED = "MITIGATED"
    ACCEPTED = "ACCEPTED"
    TRANSFERRED = "TRANSFERRED"


# ── Dataclasses ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RiskScore:
    entity_id: str
    category: RiskCategory
    score: Decimal  # I-01: 0-100 Decimal
    level: RiskLevel
    model: ScoreModel
    factors: dict
    assessed_at: datetime
    assessed_by: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass(frozen=True)
class RiskAssessment:
    id: str
    entity_id: str
    status: AssessmentStatus
    scores: list[RiskScore]
    aggregate_score: Decimal  # I-01
    created_at: datetime
    due_date: datetime
    assessor_id: str


@dataclass(frozen=True)
class RiskThreshold:
    category: RiskCategory
    low_max: Decimal  # I-01
    medium_max: Decimal  # I-01
    high_max: Decimal  # I-01
    alert_on_breach: bool


@dataclass(frozen=True)
class MitigationPlan:
    id: str
    assessment_id: str
    action: MitigationAction
    description: str
    owner: str
    due_date: datetime
    evidence_hash: str
    completed_at: datetime | None = None


@dataclass(frozen=True)
class RiskReport:
    id: str
    generated_at: datetime
    scope: str
    total_entities: int
    distribution: dict
    top_risks: list
    period_start: datetime
    period_end: datetime


# ── Protocols ────────────────────────────────────────────────────────────────


class RiskScorePort(Protocol):
    def save_score(self, s: RiskScore) -> None: ...
    def get_scores(self, entity_id: str) -> list[RiskScore]: ...
    def list_all(self) -> list[RiskScore]: ...


class AssessmentPort(Protocol):
    def save_assessment(self, a: RiskAssessment) -> None: ...
    def get_assessment(self, id: str) -> RiskAssessment | None: ...
    def list_assessments(self, entity_id: str) -> list[RiskAssessment]: ...


class MitigationPort(Protocol):
    def save_plan(self, p: MitigationPlan) -> None: ...
    def get_plan(self, id: str) -> MitigationPlan | None: ...
    def list_plans(self, assessment_id: str) -> list[MitigationPlan]: ...


class AuditPort(Protocol):
    def log(self, action: str, resource_id: str, details: dict, outcome: str) -> None: ...


# ── InMemory Stubs ────────────────────────────────────────────────────────────


class InMemoryRiskScorePort:
    def __init__(self) -> None:
        self._scores: list[RiskScore] = []
        self._seed()

    def _seed(self) -> None:
        now = datetime.now(UTC)
        self._scores = [
            RiskScore(
                entity_id="entity-seed-001",
                category=RiskCategory.AML,
                score=Decimal("45.00"),
                level=RiskLevel.MEDIUM,
                model=ScoreModel.RULE_BASED,
                factors={"pep_flag": Decimal("0"), "geo_risk": Decimal("45")},
                assessed_at=now,
                assessed_by="system",
            ),
            RiskScore(
                entity_id="entity-seed-002",
                category=RiskCategory.CREDIT,
                score=Decimal("30.00"),
                level=RiskLevel.MEDIUM,
                model=ScoreModel.WEIGHTED_AVERAGE,
                factors={"credit_score": Decimal("30")},
                assessed_at=now,
                assessed_by="system",
            ),
            RiskScore(
                entity_id="entity-seed-003",
                category=RiskCategory.FRAUD,
                score=Decimal("80.00"),
                level=RiskLevel.CRITICAL,
                model=ScoreModel.LOGISTIC_REGRESSION,
                factors={"velocity": Decimal("80")},
                assessed_at=now,
                assessed_by="system",
            ),
        ]

    def save_score(self, s: RiskScore) -> None:
        self._scores.append(s)

    def get_scores(self, entity_id: str) -> list[RiskScore]:
        return [s for s in self._scores if s.entity_id == entity_id]

    def list_all(self) -> list[RiskScore]:
        return list(self._scores)


class InMemoryAssessmentPort:
    def __init__(self) -> None:
        self._assessments: dict[str, RiskAssessment] = {}

    def save_assessment(self, a: RiskAssessment) -> None:
        self._assessments[a.id] = a

    def get_assessment(self, id: str) -> RiskAssessment | None:
        return self._assessments.get(id)

    def list_assessments(self, entity_id: str) -> list[RiskAssessment]:
        return [a for a in self._assessments.values() if a.entity_id == entity_id]


class InMemoryMitigationPort:
    def __init__(self) -> None:
        self._plans: dict[str, MitigationPlan] = {}

    def save_plan(self, p: MitigationPlan) -> None:
        self._plans[p.id] = p

    def get_plan(self, id: str) -> MitigationPlan | None:
        return self._plans.get(id)

    def list_plans(self, assessment_id: str) -> list[MitigationPlan]:
        if assessment_id == "":
            return list(self._plans.values())
        return [p for p in self._plans.values() if p.assessment_id == assessment_id]


class InMemoryAuditPort:
    def __init__(self) -> None:
        self._log: list[dict] = []

    def log(self, action: str, resource_id: str, details: dict, outcome: str) -> None:
        self._log.append(
            {
                "action": action,
                "resource_id": resource_id,
                "details": details,
                "outcome": outcome,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

    def entries(self) -> list[dict]:
        return list(self._log)
