"""
services/compliance_automation/models.py
IL-CAE-01 | Phase 23

Domain models, enums, protocols, and InMemory stubs for the Compliance Automation Engine.
Append-only audit trail (I-24). HITL for FCA breach reporting (I-27).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Protocol, runtime_checkable

# ── Enums ──────────────────────────────────────────────────────────────────────


class RuleType(str, Enum):
    AML = "AML"
    KYC = "KYC"
    SANCTIONS = "SANCTIONS"
    PEP = "PEP"
    DATA_RETENTION = "DATA_RETENTION"
    REPORTING = "REPORTING"
    POLICY = "POLICY"


class RuleSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class CheckStatus(str, Enum):
    PASS = "PASS"  # noqa: S105
    FAIL = "FAIL"
    WARNING = "WARNING"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"


class RemediationStatus(str, Enum):
    OPEN = "OPEN"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    VERIFIED = "VERIFIED"
    CLOSED = "CLOSED"


class PolicyStatus(str, Enum):
    DRAFT = "DRAFT"
    REVIEW = "REVIEW"
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


class BreachSeverity(str, Enum):
    MATERIAL = "MATERIAL"
    SIGNIFICANT = "SIGNIFICANT"
    MINOR = "MINOR"


# ── Frozen dataclasses ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ComplianceRule:
    rule_id: str
    name: str
    rule_type: RuleType
    severity: RuleSeverity
    description: str
    evaluation_logic: str
    is_active: bool
    version: int
    created_at: datetime


@dataclass(frozen=True)
class RuleSet:
    ruleset_id: str
    name: str
    rules: tuple[ComplianceRule, ...]
    created_at: datetime


@dataclass(frozen=True)
class ComplianceCheck:
    check_id: str
    entity_id: str
    rule_id: str
    status: CheckStatus
    finding: str
    evidence: str
    checked_at: datetime
    checked_by: str = "system"


@dataclass(frozen=True)
class ComplianceReport:
    report_id: str
    entity_id: str
    checks: tuple[ComplianceCheck, ...]
    overall_status: CheckStatus
    generated_at: datetime
    period_start: datetime
    period_end: datetime


@dataclass(frozen=True)
class PolicyVersion:
    version_id: str
    policy_id: str
    version_number: int
    content: str
    status: PolicyStatus
    author: str
    created_at: datetime
    approved_at: datetime | None = None


@dataclass(frozen=True)
class Remediation:
    remediation_id: str
    check_id: str
    entity_id: str
    finding: str
    status: RemediationStatus
    assigned_to: str
    due_date: datetime
    resolved_at: datetime | None = None
    created_at: datetime = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        # Allow None to be replaced with now(UTC) for frozen dataclass
        if self.created_at is None:
            object.__setattr__(self, "created_at", datetime.now(UTC))


@dataclass(frozen=True)
class BreachEvent:
    breach_id: str
    entity_id: str
    rule_id: str
    severity: BreachSeverity
    description: str
    detected_at: datetime
    reported_to_fca: bool = False
    fca_reported_at: datetime | None = None


# ── Protocols ──────────────────────────────────────────────────────────────────


@runtime_checkable
class RuleStorePort(Protocol):
    async def get_rule(self, rule_id: str) -> ComplianceRule | None: ...

    async def list_rules(
        self,
        rule_type: RuleType | None = None,
        active_only: bool = True,
    ) -> list[ComplianceRule]: ...

    async def save_rule(self, rule: ComplianceRule) -> ComplianceRule: ...


@runtime_checkable
class CheckStorePort(Protocol):
    async def save_check(self, check: ComplianceCheck) -> ComplianceCheck: ...

    async def list_checks(self, entity_id: str) -> list[ComplianceCheck]: ...


@runtime_checkable
class ReportStorePort(Protocol):
    async def save_report(self, report: ComplianceReport) -> ComplianceReport: ...

    async def get_report(self, report_id: str) -> ComplianceReport | None: ...

    async def list_reports(self, entity_id: str) -> list[ComplianceReport]: ...


@runtime_checkable
class RemediationStorePort(Protocol):
    async def save_remediation(self, r: Remediation) -> Remediation: ...

    async def get_remediation(self, remediation_id: str) -> Remediation | None: ...

    async def list_remediations(
        self,
        entity_id: str | None = None,
        status: RemediationStatus | None = None,
    ) -> list[Remediation]: ...


@runtime_checkable
class PolicyStorePort(Protocol):
    async def save_version(self, v: PolicyVersion) -> PolicyVersion: ...

    async def get_version(self, version_id: str) -> PolicyVersion | None: ...

    async def list_versions(self, policy_id: str) -> list[PolicyVersion]: ...


# ── InMemory stubs ─────────────────────────────────────────────────────────────


class InMemoryRuleStore:
    def __init__(self) -> None:
        self._rules: dict[str, ComplianceRule] = {}

    async def get_rule(self, rule_id: str) -> ComplianceRule | None:
        return self._rules.get(rule_id)

    async def list_rules(
        self,
        rule_type: RuleType | None = None,
        active_only: bool = True,
    ) -> list[ComplianceRule]:
        rules = list(self._rules.values())
        if active_only:
            rules = [r for r in rules if r.is_active]
        if rule_type is not None:
            rules = [r for r in rules if r.rule_type == rule_type]
        return rules

    async def save_rule(self, rule: ComplianceRule) -> ComplianceRule:
        self._rules[rule.rule_id] = rule
        return rule


class InMemoryCheckStore:
    def __init__(self) -> None:
        self._checks: list[ComplianceCheck] = []

    async def save_check(self, check: ComplianceCheck) -> ComplianceCheck:
        self._checks.append(check)
        return check

    async def list_checks(self, entity_id: str) -> list[ComplianceCheck]:
        return [c for c in self._checks if c.entity_id == entity_id]


class InMemoryReportStore:
    def __init__(self) -> None:
        self._reports: dict[str, ComplianceReport] = {}

    async def save_report(self, report: ComplianceReport) -> ComplianceReport:
        self._reports[report.report_id] = report
        return report

    async def get_report(self, report_id: str) -> ComplianceReport | None:
        return self._reports.get(report_id)

    async def list_reports(self, entity_id: str) -> list[ComplianceReport]:
        return [r for r in self._reports.values() if r.entity_id == entity_id]


class InMemoryRemediationStore:
    def __init__(self) -> None:
        self._remediations: dict[str, Remediation] = {}

    async def save_remediation(self, r: Remediation) -> Remediation:
        self._remediations[r.remediation_id] = r
        return r

    async def get_remediation(self, remediation_id: str) -> Remediation | None:
        return self._remediations.get(remediation_id)

    async def list_remediations(
        self,
        entity_id: str | None = None,
        status: RemediationStatus | None = None,
    ) -> list[Remediation]:
        items = list(self._remediations.values())
        if entity_id is not None:
            items = [r for r in items if r.entity_id == entity_id]
        if status is not None:
            items = [r for r in items if r.status == status]
        return items


class InMemoryPolicyStore:
    def __init__(self) -> None:
        self._versions: dict[str, PolicyVersion] = {}

    async def save_version(self, v: PolicyVersion) -> PolicyVersion:
        self._versions[v.version_id] = v
        return v

    async def get_version(self, version_id: str) -> PolicyVersion | None:
        return self._versions.get(version_id)

    async def list_versions(self, policy_id: str) -> list[PolicyVersion]:
        return [v for v in self._versions.values() if v.policy_id == policy_id]


# ── Seed data ──────────────────────────────────────────────────────────────────

_DEFAULT_RULES: list[ComplianceRule] = [
    ComplianceRule(
        rule_id="rule-aml-001",
        name="Customer AML threshold check",
        rule_type=RuleType.AML,
        severity=RuleSeverity.CRITICAL,
        description="Check customer transactions against AML thresholds (MLR 2017).",
        evaluation_logic="aml_threshold",
        is_active=True,
        version=1,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    ),
    ComplianceRule(
        rule_id="rule-kyc-001",
        name="Annual KYC review",
        rule_type=RuleType.KYC,
        severity=RuleSeverity.HIGH,
        description="Ensure annual KYC refresh for all active customers.",
        evaluation_logic="kyc_expired",
        is_active=True,
        version=1,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    ),
    ComplianceRule(
        rule_id="rule-sanctions-001",
        name="Daily sanctions screening",
        rule_type=RuleType.SANCTIONS,
        severity=RuleSeverity.CRITICAL,
        description="Screen customers against OFAC/HMT consolidated sanctions lists daily.",
        evaluation_logic="sanctions_hit",
        is_active=True,
        version=1,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    ),
    ComplianceRule(
        rule_id="rule-pep-001",
        name="Semi-annual PEP re-screening",
        rule_type=RuleType.PEP,
        severity=RuleSeverity.HIGH,
        description="Re-screen customers for Politically Exposed Person status every 180 days.",
        evaluation_logic="pep_rescreen",
        is_active=True,
        version=1,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    ),
    ComplianceRule(
        rule_id="rule-reporting-001",
        name="SUP 15.3 breach reporting",
        rule_type=RuleType.REPORTING,
        severity=RuleSeverity.HIGH,
        description="Report material operational breaches to FCA within 1 business day (SUP 15.3).",
        evaluation_logic="breach_reporting",
        is_active=True,
        version=1,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    ),
]
