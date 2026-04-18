"""
services/reporting_analytics/models.py
IL-RAP-01 | Phase 38 | banxe-emi-stack

Domain models, protocols, and in-memory stubs for Reporting & Analytics Platform.
Protocol DI: Port (Protocol) → InMemory stub (tests) → Real adapter (production)
I-01: All amounts/scores as Decimal (never float).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Protocol
import uuid

# ── Enums ────────────────────────────────────────────────────────────────────


class ReportType(str, Enum):
    COMPLIANCE = "COMPLIANCE"
    AML = "AML"
    TREASURY = "TREASURY"
    RISK = "RISK"
    CUSTOMER = "CUSTOMER"
    REGULATORY = "REGULATORY"
    OPERATIONS = "OPERATIONS"


class ReportFormat(str, Enum):
    JSON = "JSON"
    CSV = "CSV"
    PDF = "PDF"
    EXCEL = "EXCEL"


class ScheduleFrequency(str, Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    ON_DEMAND = "ON_DEMAND"


class DataSource(str, Enum):
    TRANSACTIONS = "TRANSACTIONS"
    AML_ALERTS = "AML_ALERTS"
    COMPLIANCE_EVENTS = "COMPLIANCE_EVENTS"
    TREASURY = "TREASURY"
    RISK_SCORES = "RISK_SCORES"
    CUSTOMER_DATA = "CUSTOMER_DATA"


class AggregationType(str, Enum):
    SUM = "SUM"
    AVERAGE = "AVERAGE"
    COUNT = "COUNT"
    MIN = "MIN"
    MAX = "MAX"
    PERCENTILE_95 = "PERCENTILE_95"


# ── Dataclasses ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ReportTemplate:
    id: str
    name: str
    report_type: ReportType
    sources: list[DataSource]
    parameters: dict
    format: ReportFormat
    created_by: str
    created_at: datetime


@dataclass(frozen=True)
class ReportJob:
    id: str
    template_id: str
    status: str
    parameters: dict
    output_path: str | None
    file_hash: str | None
    started_at: datetime
    completed_at: datetime | None
    error: str | None


@dataclass(frozen=True)
class ScheduledReport:
    id: str
    template_id: str
    frequency: ScheduleFrequency
    next_run: datetime
    last_run: datetime | None
    delivery: dict
    active: bool
    created_by: str


@dataclass(frozen=True)
class KPIMetric:
    name: str
    value: Decimal  # I-01
    unit: str
    period_start: datetime
    period_end: datetime
    trend: str
    sparkline: list[Decimal]


@dataclass(frozen=True)
class ExportRecord:
    id: str
    job_id: str
    format: ReportFormat
    file_hash: str
    size_bytes: int
    pii_redacted: bool
    created_at: datetime
    created_by: str


# ── Protocols ────────────────────────────────────────────────────────────────


class ReportTemplatePort(Protocol):
    def get_template(self, id: str) -> ReportTemplate | None: ...
    def save_template(self, t: ReportTemplate) -> None: ...
    def list_templates(self) -> list[ReportTemplate]: ...


class ReportJobPort(Protocol):
    def save_job(self, j: ReportJob) -> None: ...
    def get_job(self, id: str) -> ReportJob | None: ...
    def list_jobs(self, template_id: str) -> list[ReportJob]: ...


class ScheduledReportPort(Protocol):
    def save_schedule(self, s: ScheduledReport) -> None: ...
    def get_schedule(self, id: str) -> ScheduledReport | None: ...
    def list_active(self) -> list[ScheduledReport]: ...


class AuditPort(Protocol):
    def log(self, action: str, resource_id: str, details: dict, outcome: str) -> None: ...


# ── InMemory Stubs ────────────────────────────────────────────────────────────


class InMemoryReportTemplatePort:
    def __init__(self) -> None:
        self._templates: dict[str, ReportTemplate] = {}
        self._seed()

    def _seed(self) -> None:
        now = datetime.now(UTC)
        for report_type, name in [
            (ReportType.COMPLIANCE, "Monthly Compliance Report"),
            (ReportType.AML, "AML Transaction Report"),
            (ReportType.TREASURY, "Treasury Liquidity Report"),
        ]:
            tid = str(uuid.uuid4())
            template = ReportTemplate(
                id=tid,
                name=name,
                report_type=report_type,
                sources=[DataSource.TRANSACTIONS],
                parameters={"period": "monthly"},
                format=ReportFormat.JSON,
                created_by="system",
                created_at=now,
            )
            self._templates[tid] = template

    def get_template(self, id: str) -> ReportTemplate | None:
        return self._templates.get(id)

    def save_template(self, t: ReportTemplate) -> None:
        self._templates[t.id] = t

    def list_templates(self) -> list[ReportTemplate]:
        return list(self._templates.values())


class InMemoryReportJobPort:
    def __init__(self) -> None:
        self._jobs: dict[str, ReportJob] = {}

    def save_job(self, j: ReportJob) -> None:
        self._jobs[j.id] = j

    def get_job(self, id: str) -> ReportJob | None:
        return self._jobs.get(id)

    def list_jobs(self, template_id: str) -> list[ReportJob]:
        return [j for j in self._jobs.values() if j.template_id == template_id]


class InMemoryScheduledReportPort:
    def __init__(self) -> None:
        self._schedules: dict[str, ScheduledReport] = {}

    def save_schedule(self, s: ScheduledReport) -> None:
        self._schedules[s.id] = s

    def get_schedule(self, id: str) -> ScheduledReport | None:
        return self._schedules.get(id)

    def list_active(self) -> list[ScheduledReport]:
        return [s for s in self._schedules.values() if s.active]


class InMemoryAnalyticsAuditPort:
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
