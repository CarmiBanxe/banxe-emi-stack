"""tests/test_compliance_automation/test_periodic_review.py — PeriodicReview tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from services.compliance_automation.models import (
    CheckStatus,
    ComplianceCheck,
    ComplianceRule,
    InMemoryCheckStore,
    InMemoryReportStore,
    InMemoryRuleStore,
    RuleSeverity,
    RuleType,
)
from services.compliance_automation.periodic_review import PeriodicReview

_NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)


def _make_rule(
    rule_id: str,
    rule_type: RuleType,
    logic: str = "aml_threshold",
) -> ComplianceRule:
    return ComplianceRule(
        rule_id=rule_id,
        name=f"Rule {rule_id}",
        rule_type=rule_type,
        severity=RuleSeverity.HIGH,
        description="Test",
        evaluation_logic=logic,
        is_active=True,
        version=1,
        created_at=_NOW,
    )


def _make_check(
    check_id: str,
    entity_id: str,
    status: CheckStatus,
) -> ComplianceCheck:
    return ComplianceCheck(
        check_id=check_id,
        entity_id=entity_id,
        rule_id="r-1",
        status=status,
        finding="finding",
        evidence="ev",
        checked_at=_NOW,
    )


@pytest.fixture
def review():
    rule_store = InMemoryRuleStore()
    check_store = InMemoryCheckStore()
    report_store = InMemoryReportStore()
    return PeriodicReview(rule_store, check_store, report_store), rule_store


@pytest.mark.asyncio
async def test_run_customer_review_empty(review):
    rv, _ = review
    report = await rv.run_customer_review("ent-1")
    assert report.entity_id == "ent-1"
    assert report.overall_status == CheckStatus.PASS
    assert report.checks == ()


@pytest.mark.asyncio
async def test_run_customer_review_with_kyc_rule(review):
    rv, rule_store = review
    await rule_store.save_rule(_make_rule("rule-kyc-1", RuleType.KYC, "kyc_expired"))
    report = await rv.run_customer_review("ent-1")
    assert len(report.checks) == 1
    assert report.overall_status == CheckStatus.PASS


@pytest.mark.asyncio
async def test_run_customer_review_with_aml_rule(review):
    rv, rule_store = review
    await rule_store.save_rule(_make_rule("rule-aml-1", RuleType.AML, "aml_threshold"))
    report = await rv.run_customer_review("ent-1")
    assert len(report.checks) == 1
    assert report.overall_status == CheckStatus.PASS


@pytest.mark.asyncio
async def test_run_pep_screening(review):
    rv, rule_store = review
    await rule_store.save_rule(_make_rule("rule-pep-1", RuleType.PEP, "pep_rescreen"))
    report = await rv.run_pep_screening("ent-1")
    assert len(report.checks) == 1
    assert report.entity_id == "ent-1"


@pytest.mark.asyncio
async def test_run_sanctions_screening_pass(review):
    rv, rule_store = review
    await rule_store.save_rule(_make_rule("rule-safe-1", RuleType.SANCTIONS, "aml_threshold"))
    report = await rv.run_sanctions_screening("ent-1")
    assert report.overall_status == CheckStatus.PASS


@pytest.mark.asyncio
async def test_run_sanctions_screening_fail(review):
    rv, rule_store = review
    await rule_store.save_rule(_make_rule("rule-san-1", RuleType.SANCTIONS, "sanctions_hit"))
    report = await rv.run_sanctions_screening("ent-1")
    assert report.overall_status == CheckStatus.FAIL


@pytest.mark.asyncio
async def test_generate_report_all_pass(review):
    rv, _ = review
    checks = [
        _make_check("c-1", "ent-1", CheckStatus.PASS),
        _make_check("c-2", "ent-1", CheckStatus.PASS),
    ]
    report = await rv.generate_report("ent-1", checks)
    assert report.overall_status == CheckStatus.PASS


@pytest.mark.asyncio
async def test_generate_report_any_fail_gives_fail(review):
    rv, _ = review
    checks = [
        _make_check("c-1", "ent-1", CheckStatus.PASS),
        _make_check("c-2", "ent-1", CheckStatus.FAIL),
    ]
    report = await rv.generate_report("ent-1", checks)
    assert report.overall_status == CheckStatus.FAIL


@pytest.mark.asyncio
async def test_generate_report_warning_no_fail(review):
    rv, _ = review
    checks = [
        _make_check("c-1", "ent-1", CheckStatus.WARNING),
        _make_check("c-2", "ent-1", CheckStatus.PASS),
    ]
    report = await rv.generate_report("ent-1", checks)
    assert report.overall_status == CheckStatus.WARNING


@pytest.mark.asyncio
async def test_generate_report_fail_beats_warning(review):
    rv, _ = review
    checks = [
        _make_check("c-1", "ent-1", CheckStatus.WARNING),
        _make_check("c-2", "ent-1", CheckStatus.FAIL),
    ]
    report = await rv.generate_report("ent-1", checks)
    assert report.overall_status == CheckStatus.FAIL


@pytest.mark.asyncio
async def test_generate_report_has_period(review):
    rv, _ = review
    report = await rv.generate_report("ent-1", [])
    assert report.period_start < report.period_end
    delta = report.period_end - report.period_start
    assert delta.days == 30


@pytest.mark.asyncio
async def test_generate_report_saved_to_store(review):
    rv, _ = review
    rule_store = InMemoryRuleStore()
    check_store = InMemoryCheckStore()
    report_store = InMemoryReportStore()
    rv2 = PeriodicReview(rule_store, check_store, report_store)
    report = await rv2.generate_report("ent-1", [])
    fetched = await report_store.get_report(report.report_id)
    assert fetched is not None


@pytest.mark.asyncio
async def test_run_customer_review_has_report_id(review):
    rv, _ = review
    report = await rv.run_customer_review("ent-1")
    assert len(report.report_id) == 36  # UUID


@pytest.mark.asyncio
async def test_run_pep_screening_no_pep_rules_empty_checks(review):
    rv, rule_store = review
    await rule_store.save_rule(_make_rule("rule-aml-1", RuleType.AML, "aml_threshold"))
    report = await rv.run_pep_screening("ent-1")
    assert len(report.checks) == 0


@pytest.mark.asyncio
async def test_run_sanctions_ignores_aml_rules(review):
    rv, rule_store = review
    await rule_store.save_rule(_make_rule("rule-aml-1", RuleType.AML, "aml_threshold"))
    await rule_store.save_rule(_make_rule("rule-san-1", RuleType.SANCTIONS, "aml_threshold"))
    report = await rv.run_sanctions_screening("ent-1")
    assert len(report.checks) == 1
    assert report.checks[0].rule_id == "rule-san-1"
