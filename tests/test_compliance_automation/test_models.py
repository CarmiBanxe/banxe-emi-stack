"""tests/test_compliance_automation/test_models.py — Models, enums, stubs, seed data."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from services.compliance_automation.models import (
    _DEFAULT_RULES,
    BreachEvent,
    BreachSeverity,
    CheckStatus,
    ComplianceCheck,
    ComplianceReport,
    ComplianceRule,
    InMemoryCheckStore,
    InMemoryPolicyStore,
    InMemoryRemediationStore,
    InMemoryReportStore,
    InMemoryRuleStore,
    PolicyStatus,
    PolicyVersion,
    Remediation,
    RemediationStatus,
    RuleSet,
    RuleSeverity,
    RuleType,
)

_NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)


# ── Enum tests ─────────────────────────────────────────────────────────────────


def test_rule_type_values():
    assert RuleType.AML == "AML"
    assert RuleType.KYC == "KYC"
    assert RuleType.SANCTIONS == "SANCTIONS"
    assert RuleType.PEP == "PEP"
    assert RuleType.DATA_RETENTION == "DATA_RETENTION"
    assert RuleType.REPORTING == "REPORTING"
    assert RuleType.POLICY == "POLICY"


def test_rule_severity_values():
    assert RuleSeverity.CRITICAL == "CRITICAL"
    assert RuleSeverity.HIGH == "HIGH"
    assert RuleSeverity.MEDIUM == "MEDIUM"
    assert RuleSeverity.LOW == "LOW"
    assert RuleSeverity.INFO == "INFO"


def test_check_status_values():
    assert CheckStatus.PASS == "PASS"
    assert CheckStatus.FAIL == "FAIL"
    assert CheckStatus.WARNING == "WARNING"
    assert CheckStatus.SKIPPED == "SKIPPED"
    assert CheckStatus.ERROR == "ERROR"


def test_remediation_status_values():
    assert RemediationStatus.OPEN == "OPEN"
    assert RemediationStatus.ASSIGNED == "ASSIGNED"
    assert RemediationStatus.IN_PROGRESS == "IN_PROGRESS"
    assert RemediationStatus.RESOLVED == "RESOLVED"
    assert RemediationStatus.VERIFIED == "VERIFIED"
    assert RemediationStatus.CLOSED == "CLOSED"


def test_policy_status_values():
    assert PolicyStatus.DRAFT == "DRAFT"
    assert PolicyStatus.REVIEW == "REVIEW"
    assert PolicyStatus.ACTIVE == "ACTIVE"
    assert PolicyStatus.RETIRED == "RETIRED"


def test_breach_severity_values():
    assert BreachSeverity.MATERIAL == "MATERIAL"
    assert BreachSeverity.SIGNIFICANT == "SIGNIFICANT"
    assert BreachSeverity.MINOR == "MINOR"


# ── Frozen dataclass tests ─────────────────────────────────────────────────────


def test_compliance_rule_frozen():
    rule = ComplianceRule(
        rule_id="r-001",
        name="Test",
        rule_type=RuleType.AML,
        severity=RuleSeverity.HIGH,
        description="desc",
        evaluation_logic="aml_threshold",
        is_active=True,
        version=1,
        created_at=_NOW,
    )
    with pytest.raises(FrozenInstanceError):
        rule.name = "changed"  # type: ignore[misc]


def test_compliance_check_frozen():
    check = ComplianceCheck(
        check_id="c-001",
        entity_id="ent-1",
        rule_id="r-001",
        status=CheckStatus.PASS,
        finding="ok",
        evidence="ev",
        checked_at=_NOW,
    )
    assert check.checked_by == "system"
    with pytest.raises(FrozenInstanceError):
        check.status = CheckStatus.FAIL  # type: ignore[misc]


def test_compliance_check_custom_checked_by():
    check = ComplianceCheck(
        check_id="c-002",
        entity_id="ent-1",
        rule_id="r-001",
        status=CheckStatus.PASS,
        finding="ok",
        evidence="ev",
        checked_at=_NOW,
        checked_by="officer-1",
    )
    assert check.checked_by == "officer-1"


def test_compliance_report_frozen():
    report = ComplianceReport(
        report_id="rep-1",
        entity_id="ent-1",
        checks=(),
        overall_status=CheckStatus.PASS,
        generated_at=_NOW,
        period_start=_NOW,
        period_end=_NOW,
    )
    with pytest.raises(FrozenInstanceError):
        report.overall_status = CheckStatus.FAIL  # type: ignore[misc]


def test_policy_version_defaults():
    v = PolicyVersion(
        version_id="v-001",
        policy_id="pol-1",
        version_number=1,
        content="content",
        status=PolicyStatus.DRAFT,
        author="alice",
        created_at=_NOW,
    )
    assert v.approved_at is None


def test_remediation_created_at_defaults_to_now():
    r = Remediation(
        remediation_id="rem-1",
        check_id="c-001",
        entity_id="ent-1",
        finding="issue",
        status=RemediationStatus.OPEN,
        assigned_to="bob",
        due_date=_NOW,
    )
    assert r.created_at is not None
    assert r.created_at.tzinfo is not None


def test_breach_event_frozen():
    breach = BreachEvent(
        breach_id="b-001",
        entity_id="ent-1",
        rule_id="rule-aml-001",
        severity=BreachSeverity.MATERIAL,
        description="AML breach",
        detected_at=_NOW,
    )
    assert breach.reported_to_fca is False
    assert breach.fca_reported_at is None
    with pytest.raises(FrozenInstanceError):
        breach.reported_to_fca = True  # type: ignore[misc]


def test_ruleset_contains_rules():
    rule = ComplianceRule(
        rule_id="r-001",
        name="Test",
        rule_type=RuleType.AML,
        severity=RuleSeverity.HIGH,
        description="desc",
        evaluation_logic="aml_threshold",
        is_active=True,
        version=1,
        created_at=_NOW,
    )
    rs = RuleSet(ruleset_id="rs-1", name="Set", rules=(rule,), created_at=_NOW)
    assert len(rs.rules) == 1
    assert rs.rules[0].rule_id == "r-001"


# ── Seed data tests ────────────────────────────────────────────────────────────


def test_default_rules_count():
    assert len(_DEFAULT_RULES) == 5


def test_default_rules_rule_ids():
    ids = {r.rule_id for r in _DEFAULT_RULES}
    assert "rule-aml-001" in ids
    assert "rule-kyc-001" in ids
    assert "rule-sanctions-001" in ids
    assert "rule-pep-001" in ids
    assert "rule-reporting-001" in ids


def test_default_rules_aml_is_critical():
    aml = next(r for r in _DEFAULT_RULES if r.rule_id == "rule-aml-001")
    assert aml.severity == RuleSeverity.CRITICAL
    assert aml.rule_type == RuleType.AML


def test_default_rules_sanctions_is_critical():
    sanc = next(r for r in _DEFAULT_RULES if r.rule_id == "rule-sanctions-001")
    assert sanc.severity == RuleSeverity.CRITICAL
    assert sanc.rule_type == RuleType.SANCTIONS


def test_default_rules_all_active():
    assert all(r.is_active for r in _DEFAULT_RULES)


# ── InMemory stub tests ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_inmemory_rule_store_save_and_get():
    store = InMemoryRuleStore()
    rule = ComplianceRule(
        rule_id="r-test",
        name="Test Rule",
        rule_type=RuleType.KYC,
        severity=RuleSeverity.MEDIUM,
        description="desc",
        evaluation_logic="kyc_expired",
        is_active=True,
        version=1,
        created_at=_NOW,
    )
    saved = await store.save_rule(rule)
    fetched = await store.get_rule("r-test")
    assert fetched is not None
    assert fetched.rule_id == "r-test"
    assert saved.rule_id == fetched.rule_id


@pytest.mark.asyncio
async def test_inmemory_rule_store_list_active_only():
    store = InMemoryRuleStore()
    active = ComplianceRule(
        rule_id="r-active",
        name="Active",
        rule_type=RuleType.AML,
        severity=RuleSeverity.HIGH,
        description="d",
        evaluation_logic="aml_threshold",
        is_active=True,
        version=1,
        created_at=_NOW,
    )
    inactive = ComplianceRule(
        rule_id="r-inactive",
        name="Inactive",
        rule_type=RuleType.AML,
        severity=RuleSeverity.LOW,
        description="d",
        evaluation_logic="aml_threshold",
        is_active=False,
        version=1,
        created_at=_NOW,
    )
    await store.save_rule(active)
    await store.save_rule(inactive)
    result = await store.list_rules(active_only=True)
    assert len(result) == 1
    assert result[0].rule_id == "r-active"


@pytest.mark.asyncio
async def test_inmemory_check_store_save_and_list():
    store = InMemoryCheckStore()
    check = ComplianceCheck(
        check_id="c-1",
        entity_id="ent-1",
        rule_id="r-1",
        status=CheckStatus.PASS,
        finding="ok",
        evidence="ev",
        checked_at=_NOW,
    )
    await store.save_check(check)
    results = await store.list_checks("ent-1")
    assert len(results) == 1
    assert results[0].check_id == "c-1"


@pytest.mark.asyncio
async def test_inmemory_report_store():
    store = InMemoryReportStore()
    report = ComplianceReport(
        report_id="rep-1",
        entity_id="ent-1",
        checks=(),
        overall_status=CheckStatus.PASS,
        generated_at=_NOW,
        period_start=_NOW,
        period_end=_NOW,
    )
    await store.save_report(report)
    fetched = await store.get_report("rep-1")
    assert fetched is not None
    assert fetched.report_id == "rep-1"
    listed = await store.list_reports("ent-1")
    assert len(listed) == 1


@pytest.mark.asyncio
async def test_inmemory_remediation_store():
    store = InMemoryRemediationStore()
    r = Remediation(
        remediation_id="rem-1",
        check_id="c-1",
        entity_id="ent-1",
        finding="issue",
        status=RemediationStatus.OPEN,
        assigned_to="alice",
        due_date=_NOW,
        created_at=datetime.now(UTC),
    )
    await store.save_remediation(r)
    fetched = await store.get_remediation("rem-1")
    assert fetched is not None
    listed = await store.list_remediations(entity_id="ent-1")
    assert len(listed) == 1


@pytest.mark.asyncio
async def test_inmemory_policy_store():
    store = InMemoryPolicyStore()
    v = PolicyVersion(
        version_id="v-1",
        policy_id="pol-1",
        version_number=1,
        content="content",
        status=PolicyStatus.DRAFT,
        author="alice",
        created_at=_NOW,
    )
    await store.save_version(v)
    fetched = await store.get_version("v-1")
    assert fetched is not None
    listed = await store.list_versions("pol-1")
    assert len(listed) == 1
