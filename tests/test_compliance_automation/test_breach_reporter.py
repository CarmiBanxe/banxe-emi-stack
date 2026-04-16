"""tests/test_compliance_automation/test_breach_reporter.py — BreachReporter tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from services.compliance_automation.breach_reporter import BreachReporter
from services.compliance_automation.models import (
    BreachSeverity,
    CheckStatus,
    ComplianceCheck,
    InMemoryCheckStore,
    InMemoryReportStore,
)

_NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)


def _make_check(check_id: str, rule_id: str, status: CheckStatus) -> ComplianceCheck:
    return ComplianceCheck(
        check_id=check_id,
        entity_id="ent-1",
        rule_id=rule_id,
        status=status,
        finding=f"Finding for {rule_id}",
        evidence="ev",
        checked_at=_NOW,
    )


@pytest.fixture
def reporter():
    return BreachReporter(InMemoryCheckStore(), InMemoryReportStore())


@pytest.mark.asyncio
async def test_detect_breaches_empty_checks(reporter):
    breaches = await reporter.detect_breaches("ent-1", [])
    assert breaches == []


@pytest.mark.asyncio
async def test_detect_breaches_pass_checks_no_breach(reporter):
    checks = [_make_check("c-1", "rule-aml-001", CheckStatus.PASS)]
    breaches = await reporter.detect_breaches("ent-1", checks)
    assert breaches == []


@pytest.mark.asyncio
async def test_detect_breaches_fail_aml_is_material(reporter):
    checks = [_make_check("c-1", "rule-aml-001", CheckStatus.FAIL)]
    breaches = await reporter.detect_breaches("ent-1", checks)
    assert len(breaches) == 1
    assert breaches[0].severity == BreachSeverity.MATERIAL


@pytest.mark.asyncio
async def test_detect_breaches_fail_sanctions_is_material(reporter):
    checks = [_make_check("c-1", "rule-sanctions-001", CheckStatus.FAIL)]
    breaches = await reporter.detect_breaches("ent-1", checks)
    assert len(breaches) == 1
    assert breaches[0].severity == BreachSeverity.MATERIAL


@pytest.mark.asyncio
async def test_detect_breaches_fail_kyc_is_significant(reporter):
    checks = [_make_check("c-1", "rule-kyc-001", CheckStatus.FAIL)]
    breaches = await reporter.detect_breaches("ent-1", checks)
    assert len(breaches) == 1
    assert breaches[0].severity == BreachSeverity.SIGNIFICANT


@pytest.mark.asyncio
async def test_detect_breaches_fail_pep_is_significant(reporter):
    checks = [_make_check("c-1", "rule-pep-001", CheckStatus.FAIL)]
    breaches = await reporter.detect_breaches("ent-1", checks)
    assert len(breaches) == 1
    assert breaches[0].severity == BreachSeverity.SIGNIFICANT


@pytest.mark.asyncio
async def test_detect_breaches_other_rule_is_minor(reporter):
    checks = [_make_check("c-1", "rule-reporting-001", CheckStatus.FAIL)]
    breaches = await reporter.detect_breaches("ent-1", checks)
    assert len(breaches) == 1
    assert breaches[0].severity == BreachSeverity.MINOR


@pytest.mark.asyncio
async def test_detect_breaches_multiple_fails(reporter):
    checks = [
        _make_check("c-1", "rule-aml-001", CheckStatus.FAIL),
        _make_check("c-2", "rule-kyc-001", CheckStatus.FAIL),
        _make_check("c-3", "rule-pep-001", CheckStatus.PASS),
    ]
    breaches = await reporter.detect_breaches("ent-1", checks)
    assert len(breaches) == 2


@pytest.mark.asyncio
async def test_detect_breaches_has_entity_id(reporter):
    checks = [_make_check("c-1", "rule-aml-001", CheckStatus.FAIL)]
    breaches = await reporter.detect_breaches("ent-xyz", checks)
    assert breaches[0].entity_id == "ent-xyz"


@pytest.mark.asyncio
async def test_detect_breaches_not_reported_by_default(reporter):
    checks = [_make_check("c-1", "rule-aml-001", CheckStatus.FAIL)]
    breaches = await reporter.detect_breaches("ent-1", checks)
    assert breaches[0].reported_to_fca is False
    assert breaches[0].fca_reported_at is None


@pytest.mark.asyncio
async def test_report_to_fca_marks_reported(reporter):
    checks = [_make_check("c-1", "rule-aml-001", CheckStatus.FAIL)]
    breaches = await reporter.detect_breaches("ent-1", checks)
    updated = await reporter.report_to_fca(breaches[0], "officer-1")
    assert updated.reported_to_fca is True
    assert updated.fca_reported_at is not None


@pytest.mark.asyncio
async def test_get_pending_breaches_all_unreported(reporter):
    checks = [
        _make_check("c-1", "rule-aml-001", CheckStatus.FAIL),
        _make_check("c-2", "rule-kyc-001", CheckStatus.FAIL),
    ]
    await reporter.detect_breaches("ent-1", checks)
    pending = await reporter.get_pending_breaches()
    assert len(pending) == 2


@pytest.mark.asyncio
async def test_get_pending_breaches_excludes_reported(reporter):
    checks = [
        _make_check("c-1", "rule-aml-001", CheckStatus.FAIL),
        _make_check("c-2", "rule-kyc-001", CheckStatus.FAIL),
    ]
    breaches = await reporter.detect_breaches("ent-1", checks)
    await reporter.report_to_fca(breaches[0], "officer")
    pending = await reporter.get_pending_breaches()
    assert len(pending) == 1


@pytest.mark.asyncio
async def test_get_pending_breaches_filtered_by_entity(reporter):
    checks_ent1 = [_make_check("c-1", "rule-aml-001", CheckStatus.FAIL)]
    checks_ent2 = [
        ComplianceCheck(
            check_id="c-2",
            entity_id="ent-2",
            rule_id="rule-kyc-001",
            status=CheckStatus.FAIL,
            finding="issue",
            evidence="ev",
            checked_at=_NOW,
        )
    ]
    await reporter.detect_breaches("ent-1", checks_ent1)
    await reporter.detect_breaches("ent-2", checks_ent2)
    pending = await reporter.get_pending_breaches(entity_id="ent-1")
    assert len(pending) == 1
    assert pending[0].entity_id == "ent-1"
