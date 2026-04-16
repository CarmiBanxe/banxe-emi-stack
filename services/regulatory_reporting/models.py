"""
services/regulatory_reporting/models.py — Data models and Protocol ports
IL-RRA-01 | Phase 14 | banxe-emi-stack

Shared across all regulatory reporting services.
Protocol DI: Port (Protocol) → InMemory stub (tests) → Real adapter (production)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Protocol
import uuid

# ─── Enums ────────────────────────────────────────────────────────────────────


class ReportType(str, Enum):
    FIN060 = "FIN060"  # FCA CASS 15 safeguarding return — SUP 16
    FIN071 = "FIN071"  # FCA client assets annual return — SUP 16
    FSA076 = "FSA076"  # FCA regulated fees data — SUP 16
    SAR_BATCH = "SAR_BATCH"  # HMRC/NCA SAR batch — POCA 2002 s.330
    BOE_FORM_BT = "BOE_FORM_BT"  # BoE statistical Form BT
    ACPR_EMI = "ACPR_EMI"  # ACPR France EMI quarterly — ACPR 2014-P-01


class ReportStatus(str, Enum):
    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    SUBMITTED = "SUBMITTED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class RegulatorTarget(str, Enum):
    FCA_REGDATA = "FCA_REGDATA"  # FCA RegData portal
    NCA_GATEWAY = "NCA_GATEWAY"  # UK NCA SAR Online gateway
    BOE_STATISTICAL = "BOE_STATISTICAL"  # Bank of England statistical portal
    ACPR_PORTAL = "ACPR_PORTAL"  # French ACPR portal


class ScheduleFrequency(str, Enum):
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    ANNUALLY = "ANNUALLY"
    WEEKLY = "WEEKLY"


# ─── Data classes ─────────────────────────────────────────────────────────────


@dataclass
class ReportPeriod:
    start: datetime
    end: datetime

    @property
    def label(self) -> str:
        return f"{self.start.strftime('%Y-%m')}_to_{self.end.strftime('%Y-%m')}"


@dataclass
class ReportRequest:
    report_type: ReportType
    period: ReportPeriod
    entity_id: str  # EMI firm reference number
    entity_name: str
    submitter_id: str  # user/agent submitting
    template_version: str = "v1"
    metadata: dict = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ReportResult:
    request_id: str
    report_type: ReportType
    status: ReportStatus
    xml_content: str | None  # generated XML
    pdf_content: bytes | None  # optional PDF export
    validation_errors: list[str]
    submission_ref: str | None  # regulator reference on acceptance
    generated_at: datetime
    submitted_at: datetime | None = None
    regulator_target: RegulatorTarget | None = None

    @property
    def is_ready_to_submit(self) -> bool:
        return self.status == ReportStatus.VALIDATED and not self.validation_errors


@dataclass(frozen=True)
class ValidationResult:
    is_valid: bool
    errors: list[str]
    warnings: list[str]
    schema_version: str
    validated_at: datetime


@dataclass(frozen=True)
class AuditEntry:
    """Immutable audit record — I-24 append-only."""

    id: str
    event_type: str  # report.generated / report.validated / report.submitted
    report_type: ReportType
    report_id: str
    entity_id: str
    actor: str
    status: ReportStatus
    details: dict
    created_at: datetime
    regulator_target: RegulatorTarget | None = None


@dataclass
class ScheduledReport:
    id: str
    report_type: ReportType
    entity_id: str
    frequency: ScheduleFrequency
    next_run_at: datetime
    template_version: str
    is_active: bool = True
    n8n_workflow_id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class ReportTemplate:
    report_type: ReportType
    version: str
    description: str
    regulator: RegulatorTarget
    xsd_schema: str  # schema file path or content
    jinja_template: str  # template name


# ─── Protocol ports ───────────────────────────────────────────────────────────


class XMLGeneratorPort(Protocol):
    """Generate regulatory XML from structured data."""

    async def generate(
        self,
        request: ReportRequest,
        financial_data: dict,
    ) -> str: ...


class ValidatorPort(Protocol):
    """Validate XML against XSD schema."""

    async def validate(
        self,
        xml_content: str,
        report_type: ReportType,
    ) -> ValidationResult: ...


class AuditTrailPort(Protocol):
    """Append-only regulatory audit trail — SYSC 9."""

    async def append(self, entry: AuditEntry) -> None: ...
    async def query(
        self,
        report_type: ReportType | None = None,
        entity_id: str | None = None,
        days: int = 30,
    ) -> list[AuditEntry]: ...


class SchedulerPort(Protocol):
    """Schedule recurring regulatory reports via n8n."""

    async def schedule(self, report: ScheduledReport) -> bool: ...
    async def cancel(self, schedule_id: str) -> bool: ...
    async def list_active(self, entity_id: str) -> list[ScheduledReport]: ...


class RegulatorGatewayPort(Protocol):
    """Submit reports to regulator portals."""

    async def submit(
        self,
        result: ReportResult,
        target: RegulatorTarget,
    ) -> str: ...  # returns submission reference


# ─── InMemory stubs ───────────────────────────────────────────────────────────


class InMemoryXMLGenerator:
    """Stub: returns deterministic XML for tests."""

    async def generate(self, request: ReportRequest, financial_data: dict) -> str:
        return (
            f'<?xml version="1.0" encoding="UTF-8"?>'
            f"<Report>"
            f"<Type>{request.report_type.value}</Type>"
            f"<Entity>{request.entity_id}</Entity>"
            f"<Period>{request.period.label}</Period>"
            f"<TotalAssets>{financial_data.get('total_assets', '0')}</TotalAssets>"
            f"</Report>"
        )


class InMemoryValidator:
    """Stub: always returns valid for tests (override for error cases)."""

    def __init__(self, *, force_errors: list[str] | None = None) -> None:
        self._errors = force_errors or []

    async def validate(self, xml_content: str, report_type: ReportType) -> ValidationResult:
        return ValidationResult(
            is_valid=not self._errors,
            errors=self._errors,
            warnings=[],
            schema_version="xsd-1.0",
            validated_at=datetime.now(UTC),
        )


class InMemoryAuditTrail:
    """Stub: in-memory append-only log for tests."""

    def __init__(self) -> None:
        self.entries: list[AuditEntry] = []

    async def append(self, entry: AuditEntry) -> None:
        self.entries.append(entry)

    async def query(
        self,
        report_type: ReportType | None = None,
        entity_id: str | None = None,
        days: int = 30,
    ) -> list[AuditEntry]:
        since = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        results = self.entries
        if report_type:
            results = [e for e in results if e.report_type == report_type]
        if entity_id:
            results = [e for e in results if e.entity_id == entity_id]
        return results


class InMemoryScheduler:
    """Stub: tracks scheduled reports in memory."""

    def __init__(self, *, should_succeed: bool = True) -> None:
        self._succeed = should_succeed
        self.scheduled: list[ScheduledReport] = []
        self.cancelled: list[str] = []

    async def schedule(self, report: ScheduledReport) -> bool:
        if self._succeed:
            self.scheduled.append(report)
        return self._succeed

    async def cancel(self, schedule_id: str) -> bool:
        self.cancelled.append(schedule_id)
        return True

    async def list_active(self, entity_id: str) -> list[ScheduledReport]:
        return [s for s in self.scheduled if s.entity_id == entity_id and s.is_active]


class InMemoryRegulatorGateway:
    """Stub: simulates regulator portal acceptance."""

    def __init__(self, *, should_accept: bool = True) -> None:
        self._accept = should_accept
        self.submissions: list[tuple[str, RegulatorTarget]] = []

    async def submit(self, result: ReportResult, target: RegulatorTarget) -> str:
        ref = f"REF-{result.request_id[:8].upper()}"
        self.submissions.append((ref, target))
        if not self._accept:
            raise ValueError(f"Regulator rejected submission: {ref}")
        return ref


# ─── Template registry ────────────────────────────────────────────────────────


REPORT_TEMPLATES: dict[ReportType, ReportTemplate] = {
    ReportType.FIN060: ReportTemplate(
        report_type=ReportType.FIN060,
        version="v3",
        description="FCA CASS 15 Monthly Safeguarding Return — SUP 16.12",
        regulator=RegulatorTarget.FCA_REGDATA,
        xsd_schema="schemas/fin060_v3.xsd",
        jinja_template="fin060.xml.j2",
    ),
    ReportType.FIN071: ReportTemplate(
        report_type=ReportType.FIN071,
        version="v2",
        description="FCA Client Assets Annual Return — SUP 16.12",
        regulator=RegulatorTarget.FCA_REGDATA,
        xsd_schema="schemas/fin071_v2.xsd",
        jinja_template="fin071.xml.j2",
    ),
    ReportType.FSA076: ReportTemplate(
        report_type=ReportType.FSA076,
        version="v1",
        description="FCA Regulated Fees Data — SUP 16.20",
        regulator=RegulatorTarget.FCA_REGDATA,
        xsd_schema="schemas/fsa076_v1.xsd",
        jinja_template="fsa076.xml.j2",
    ),
    ReportType.SAR_BATCH: ReportTemplate(
        report_type=ReportType.SAR_BATCH,
        version="v2",
        description="NCA SAR Batch Filing — POCA 2002 s.330",
        regulator=RegulatorTarget.NCA_GATEWAY,
        xsd_schema="schemas/sar_batch_v2.xsd",
        jinja_template="sar_batch.xml.j2",
    ),
    ReportType.BOE_FORM_BT: ReportTemplate(
        report_type=ReportType.BOE_FORM_BT,
        version="v1",
        description="Bank of England Form BT Statistical Return",
        regulator=RegulatorTarget.BOE_STATISTICAL,
        xsd_schema="schemas/boe_form_bt_v1.xsd",
        jinja_template="boe_form_bt.xml.j2",
    ),
    ReportType.ACPR_EMI: ReportTemplate(
        report_type=ReportType.ACPR_EMI,
        version="v1",
        description="ACPR France EMI Quarterly Return — ACPR 2014-P-01",
        regulator=RegulatorTarget.ACPR_PORTAL,
        xsd_schema="schemas/acpr_emi_v1.xsd",
        jinja_template="acpr_emi.xml.j2",
    ),
}

# SLA hours per report type (regulatory filing deadlines)
FILING_SLA_DAYS: dict[ReportType, int] = {
    ReportType.FIN060: 15,  # 15th of following month
    ReportType.FIN071: 30,  # 30 days after period end
    ReportType.FSA076: 30,  # 30 days after period end
    ReportType.SAR_BATCH: 1,  # SAR must be filed within 24h of decision
    ReportType.BOE_FORM_BT: 25,  # 25th of following month
    ReportType.ACPR_EMI: 45,  # 45 days after quarter end
}

# Amount type alias for clarity — I-01: always Decimal
ReportAmount = Decimal
