"""
services/audit_dashboard/models.py
IL-AGD-01 | Phase 16 | banxe-emi-stack

Core domain models, Protocol DI ports, and InMemory stubs for the
Audit & Governance Dashboard.  All risk/compliance scores are Python
float (0.0–100.0 percentages) — NOT monetary Decimal.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Protocol

# ── Enums ────────────────────────────────────────────────────────────────────


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class EventCategory(str, Enum):
    AML = "AML"
    KYC = "KYC"
    PAYMENT = "PAYMENT"
    LEDGER = "LEDGER"
    AUTH = "AUTH"
    COMPLIANCE = "COMPLIANCE"
    SAFEGUARDING = "SAFEGUARDING"
    REGULATORY = "REGULATORY"


class ReportFormat(str, Enum):
    JSON = "JSON"
    PDF = "PDF"


class GovernanceStatus(str, Enum):
    COMPLIANT = "COMPLIANT"
    REQUIRES_ATTENTION = "REQUIRES_ATTENTION"
    NON_COMPLIANT = "NON_COMPLIANT"


# ── Dataclasses ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AuditEvent:
    """Unified audit event across all services."""

    id: str
    category: EventCategory
    event_type: str
    entity_id: str
    actor: str
    details: dict
    risk_level: RiskLevel
    created_at: datetime
    source_service: str


@dataclass(frozen=True)
class GovernanceReport:
    """Governance/compliance report (JSON or PDF)."""

    id: str
    title: str
    period_start: datetime
    period_end: datetime
    generated_at: datetime
    format: ReportFormat
    content: dict
    total_events: int
    risk_summary: dict
    compliance_score: float  # 0.0–100.0 percentage, NOT money


@dataclass(frozen=True)
class RiskScore:
    """Multi-dimensional risk score for an entity.  All fields 0.0–100.0."""

    entity_id: str
    computed_at: datetime
    aml_score: float
    fraud_score: float
    operational_score: float
    regulatory_score: float
    overall_score: float
    contributing_factors: list[str]


@dataclass(frozen=True)
class ComplianceMetric:
    """A single measured compliance KPI."""

    metric_id: str
    name: str
    category: EventCategory
    value: float
    threshold: float
    status: GovernanceStatus
    measured_at: datetime
    details: dict


@dataclass(frozen=True)
class DashboardMetrics:
    """Aggregated live metrics for the governance dashboard."""

    generated_at: datetime
    total_events_24h: int
    high_risk_events: int
    compliance_score: float  # 0.0–100.0 percentage, NOT money
    active_consents: int
    pending_hitl: int
    safeguarding_status: str
    risk_by_category: dict


# ── Protocol Ports ────────────────────────────────────────────────────────────


class EventStorePort(Protocol):
    async def query_events(
        self,
        category: EventCategory | None = None,
        entity_id: str | None = None,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
        risk_level: RiskLevel | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]: ...

    async def ingest(self, event: AuditEvent) -> None: ...


class ReportStorePort(Protocol):
    async def save_report(self, report: GovernanceReport) -> None: ...

    async def get_report(self, report_id: str) -> GovernanceReport | None: ...

    async def list_reports(self, limit: int = 20) -> list[GovernanceReport]: ...


class RiskEnginePort(Protocol):
    async def compute_score(self, entity_id: str, events: list[AuditEvent]) -> RiskScore: ...


class MetricsStorePort(Protocol):
    async def get_dashboard_metrics(self) -> DashboardMetrics: ...

    async def update_metric(self, metric: ComplianceMetric) -> None: ...


# ── InMemory Stubs ────────────────────────────────────────────────────────────


class InMemoryEventStore:
    """List-backed event store with filter support for tests."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    async def ingest(self, event: AuditEvent) -> None:
        self._events.append(event)

    async def query_events(
        self,
        category: EventCategory | None = None,
        entity_id: str | None = None,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
        risk_level: RiskLevel | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        result = list(self._events)
        if category is not None:
            result = [e for e in result if e.category == category]
        if entity_id is not None:
            result = [e for e in result if e.entity_id == entity_id]
        if from_dt is not None:
            result = [e for e in result if e.created_at >= from_dt]
        if to_dt is not None:
            result = [e for e in result if e.created_at <= to_dt]
        if risk_level is not None:
            result = [e for e in result if e.risk_level == risk_level]
        return result[:limit]


class InMemoryReportStore:
    """Dict-backed report store for tests."""

    def __init__(self) -> None:
        self._reports: dict[str, GovernanceReport] = {}

    async def save_report(self, report: GovernanceReport) -> None:
        self._reports[report.id] = report

    async def get_report(self, report_id: str) -> GovernanceReport | None:
        return self._reports.get(report_id)

    async def list_reports(self, limit: int = 20) -> list[GovernanceReport]:
        reports = list(self._reports.values())
        return reports[:limit]


class InMemoryRiskEngine:
    """Deterministic risk engine: more events → higher scores (0–100)."""

    async def compute_score(self, entity_id: str, events: list[AuditEvent]) -> RiskScore:
        count = len(events)
        critical_count = sum(1 for e in events if e.risk_level == RiskLevel.CRITICAL)
        high_count = sum(1 for e in events if e.risk_level == RiskLevel.HIGH)

        base = min(count * 3.0, 60.0)
        crit_boost = min(critical_count * 10.0, 30.0)
        high_boost = min(high_count * 5.0, 20.0)

        aml = min(base + crit_boost, 100.0)
        fraud = min(base + high_boost, 100.0)
        operational = min(base * 0.8, 100.0)
        regulatory = min(base * 0.6 + crit_boost * 0.5, 100.0)
        overall = min((aml + fraud + operational + regulatory) / 4.0, 100.0)

        factors: list[str] = []
        if critical_count > 0:
            factors.append(f"{critical_count} CRITICAL event(s)")
        if high_count > 0:
            factors.append(f"{high_count} HIGH risk event(s)")
        if count > 10:
            factors.append(f"High event volume ({count})")

        return RiskScore(
            entity_id=entity_id,
            computed_at=datetime.now(UTC),
            aml_score=round(aml, 2),
            fraud_score=round(fraud, 2),
            operational_score=round(operational, 2),
            regulatory_score=round(regulatory, 2),
            overall_score=round(overall, 2),
            contributing_factors=factors,
        )


class InMemoryMetricsStore:
    """Returns sample DashboardMetrics for tests."""

    def __init__(self) -> None:
        self._metrics: dict[str, ComplianceMetric] = {}

    async def get_dashboard_metrics(self) -> DashboardMetrics:
        return DashboardMetrics(
            generated_at=datetime.now(UTC),
            total_events_24h=42,
            high_risk_events=3,
            compliance_score=91.5,
            active_consents=128,
            pending_hitl=2,
            safeguarding_status="COMPLIANT",
            risk_by_category={c.value: 0 for c in EventCategory},
        )

    async def update_metric(self, metric: ComplianceMetric) -> None:
        self._metrics[metric.metric_id] = metric


__all__ = [
    "AuditEvent",
    "ComplianceMetric",
    "DashboardMetrics",
    "EventCategory",
    "EventStorePort",
    "GovernanceReport",
    "GovernanceStatus",
    "InMemoryEventStore",
    "InMemoryMetricsStore",
    "InMemoryReportStore",
    "InMemoryRiskEngine",
    "MetricsStorePort",
    "ReportFormat",
    "ReportStorePort",
    "RiskEnginePort",
    "RiskLevel",
    "RiskScore",
]
