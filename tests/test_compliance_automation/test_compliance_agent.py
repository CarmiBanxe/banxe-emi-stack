"""tests/test_compliance_automation/test_compliance_agent.py — Agent integration tests."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from services.compliance_automation.breach_reporter import BreachReporter
from services.compliance_automation.compliance_automation_agent import (
    ComplianceAutomationAgent,
)
from services.compliance_automation.models import (
    _DEFAULT_RULES,
    InMemoryCheckStore,
    InMemoryPolicyStore,
    InMemoryRemediationStore,
    InMemoryReportStore,
    InMemoryRuleStore,
    PolicyStatus,
    PolicyVersion,
)
from services.compliance_automation.periodic_review import PeriodicReview
from services.compliance_automation.policy_manager import PolicyManager
from services.compliance_automation.remediation_tracker import RemediationTracker
from services.compliance_automation.rule_engine import RuleEngine

_NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)


def _make_agent() -> ComplianceAutomationAgent:
    rule_store = InMemoryRuleStore()
    check_store = InMemoryCheckStore()
    report_store = InMemoryReportStore()
    remediation_store = InMemoryRemediationStore()
    policy_store = InMemoryPolicyStore()

    for rule in _DEFAULT_RULES:
        rule_store._rules[rule.rule_id] = rule  # noqa: SLF001

    rule_engine = RuleEngine(rule_store, check_store)
    policy_manager = PolicyManager(policy_store)
    periodic_review = PeriodicReview(rule_store, check_store, report_store)
    breach_reporter = BreachReporter(check_store, report_store)
    remediation_tracker = RemediationTracker(remediation_store)

    return ComplianceAutomationAgent(
        rule_engine=rule_engine,
        policy_manager=policy_manager,
        periodic_review=periodic_review,
        breach_reporter=breach_reporter,
        remediation_tracker=remediation_tracker,
    )


@pytest.mark.asyncio
async def test_evaluate_compliance_returns_dict():
    agent = _make_agent()
    result = await agent.evaluate_compliance("ent-1")
    assert "checks" in result
    assert "breaches" in result
    assert "overall_status" in result


@pytest.mark.asyncio
async def test_evaluate_compliance_has_default_rules():
    agent = _make_agent()
    result = await agent.evaluate_compliance("ent-1")
    assert len(result["checks"]) == 5  # 5 default rules


@pytest.mark.asyncio
async def test_evaluate_compliance_sanctions_causes_fail():
    agent = _make_agent()
    result = await agent.evaluate_compliance("ent-1", rule_ids=["rule-sanctions-001"])
    assert result["overall_status"] == "FAIL"
    assert len(result["breaches"]) == 1


@pytest.mark.asyncio
async def test_evaluate_compliance_aml_passes():
    agent = _make_agent()
    result = await agent.evaluate_compliance("ent-1", rule_ids=["rule-aml-001"])
    assert result["overall_status"] == "PASS"
    assert result["breaches"] == []


@pytest.mark.asyncio
async def test_get_rules_returns_list():
    agent = _make_agent()
    rules = await agent.get_rules()
    assert len(rules) == 5


@pytest.mark.asyncio
async def test_get_rules_filtered_by_type():
    agent = _make_agent()
    rules = await agent.get_rules(rule_type="AML")
    assert len(rules) == 1
    assert rules[0]["rule_type"] == "AML"


@pytest.mark.asyncio
async def test_get_rules_invalid_type_raises():
    agent = _make_agent()
    with pytest.raises(ValueError):
        await agent.get_rules(rule_type="INVALID_TYPE")


@pytest.mark.asyncio
async def test_report_breach_always_hitl_required():
    agent = _make_agent()
    result = await agent.report_breach("breach-1", "officer-1")
    assert result["status"] == "HITL_REQUIRED"
    assert "FCA" in result["reason"]


@pytest.mark.asyncio
async def test_report_breach_never_auto_submits():
    agent = _make_agent()
    result1 = await agent.report_breach("breach-1", "officer-1")
    result2 = await agent.report_breach("breach-2", "officer-2")
    assert result1["status"] == "HITL_REQUIRED"
    assert result2["status"] == "HITL_REQUIRED"


@pytest.mark.asyncio
async def test_track_remediation_returns_dict():
    agent = _make_agent()
    result = await agent.track_remediation(
        check_id="c-1",
        entity_id="ent-1",
        finding="Issue found",
        assigned_to="alice",
        due_days=30,
    )
    assert "remediation_id" in result
    assert result["status"] == "OPEN"
    assert result["entity_id"] == "ent-1"


@pytest.mark.asyncio
async def test_create_policy_returns_dict():
    agent = _make_agent()
    result = await agent.create_policy("pol-1", "policy content", "alice")
    assert result["policy_id"] == "pol-1"
    assert result["status"] == "DRAFT"
    assert result["author"] == "alice"


@pytest.mark.asyncio
async def test_get_policy_diff():
    agent = _make_agent()
    policy_store = InMemoryPolicyStore()
    pm = PolicyManager(policy_store)
    await pm.create_policy("pol-diff", "content A", "alice")
    await policy_store.save_version(
        PolicyVersion(
            version_id=str(uuid4()),
            policy_id="pol-diff",
            version_number=2,
            content="content B",
            status=PolicyStatus.DRAFT,
            author="bob",
            created_at=datetime.now(UTC),
        )
    )
    agent2 = ComplianceAutomationAgent(
        rule_engine=RuleEngine(InMemoryRuleStore(), InMemoryCheckStore()),
        policy_manager=pm,
        periodic_review=PeriodicReview(
            InMemoryRuleStore(), InMemoryCheckStore(), InMemoryReportStore()
        ),
        breach_reporter=BreachReporter(InMemoryCheckStore(), InMemoryReportStore()),
        remediation_tracker=RemediationTracker(InMemoryRemediationStore()),
    )
    diff = await agent2.get_policy_diff("pol-diff", 1, 2)
    assert diff["changed"] is True
    assert diff["v1_content"] == "content A"
