"""tests/test_compliance_automation/test_rule_engine.py — RuleEngine tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from services.compliance_automation.models import (
    CheckStatus,
    ComplianceRule,
    InMemoryCheckStore,
    InMemoryRuleStore,
    RuleSeverity,
    RuleType,
)
from services.compliance_automation.rule_engine import RuleEngine

_NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)


def _make_rule(
    rule_id: str,
    rule_type: RuleType = RuleType.AML,
    logic: str = "aml_threshold",
    is_active: bool = True,
) -> ComplianceRule:
    return ComplianceRule(
        rule_id=rule_id,
        name=f"Rule {rule_id}",
        rule_type=rule_type,
        severity=RuleSeverity.HIGH,
        description="Test rule",
        evaluation_logic=logic,
        is_active=is_active,
        version=1,
        created_at=_NOW,
    )


@pytest.fixture
def stores():
    rule_store = InMemoryRuleStore()
    check_store = InMemoryCheckStore()
    return rule_store, check_store


@pytest.fixture
def engine(stores):
    rule_store, check_store = stores
    return RuleEngine(rule_store, check_store), rule_store, check_store


@pytest.mark.asyncio
async def test_evaluate_entity_no_rules_returns_empty(engine):
    eng, _, _ = engine
    checks = await eng.evaluate_entity("ent-1")
    assert checks == []


@pytest.mark.asyncio
async def test_evaluate_entity_aml_passes(engine):
    eng, rule_store, _ = engine
    await rule_store.save_rule(_make_rule("r-aml-1", logic="aml_threshold"))
    checks = await eng.evaluate_entity("ent-1")
    assert len(checks) == 1
    assert checks[0].status == CheckStatus.PASS


@pytest.mark.asyncio
async def test_evaluate_entity_kyc_passes(engine):
    eng, rule_store, _ = engine
    await rule_store.save_rule(_make_rule("r-kyc-1", rule_type=RuleType.KYC, logic="kyc_expired"))
    checks = await eng.evaluate_entity("ent-1")
    assert checks[0].status == CheckStatus.PASS


@pytest.mark.asyncio
async def test_evaluate_entity_sanctions_fails(engine):
    eng, rule_store, _ = engine
    await rule_store.save_rule(
        _make_rule("r-san-1", rule_type=RuleType.SANCTIONS, logic="sanctions_hit")
    )
    checks = await eng.evaluate_entity("ent-1")
    assert len(checks) == 1
    assert checks[0].status == CheckStatus.FAIL
    assert "Sanctions" in checks[0].finding


@pytest.mark.asyncio
async def test_evaluate_entity_unknown_logic_passes(engine):
    eng, rule_store, _ = engine
    await rule_store.save_rule(_make_rule("r-unk-1", logic="some_other_logic"))
    checks = await eng.evaluate_entity("ent-1")
    assert checks[0].status == CheckStatus.PASS


@pytest.mark.asyncio
async def test_evaluate_entity_filters_by_rule_ids(engine):
    eng, rule_store, _ = engine
    await rule_store.save_rule(_make_rule("r-1"))
    await rule_store.save_rule(_make_rule("r-2"))
    checks = await eng.evaluate_entity("ent-1", rule_ids=["r-1"])
    assert len(checks) == 1
    assert checks[0].rule_id == "r-1"


@pytest.mark.asyncio
async def test_evaluate_entity_skips_inactive_rules(engine):
    eng, rule_store, _ = engine
    await rule_store.save_rule(_make_rule("r-active"))
    await rule_store.save_rule(_make_rule("r-inactive", is_active=False))
    checks = await eng.evaluate_entity("ent-1")
    assert len(checks) == 1
    assert checks[0].rule_id == "r-active"


@pytest.mark.asyncio
async def test_evaluate_entity_saves_checks_to_store(engine):
    eng, rule_store, check_store = engine
    await rule_store.save_rule(_make_rule("r-1"))
    await eng.evaluate_entity("ent-1")
    saved = await check_store.list_checks("ent-1")
    assert len(saved) == 1


@pytest.mark.asyncio
async def test_evaluate_entity_check_has_entity_id(engine):
    eng, rule_store, _ = engine
    await rule_store.save_rule(_make_rule("r-1"))
    checks = await eng.evaluate_entity("ent-xyz")
    assert checks[0].entity_id == "ent-xyz"


@pytest.mark.asyncio
async def test_evaluate_entity_check_has_uuid_check_id(engine):
    eng, rule_store, _ = engine
    await rule_store.save_rule(_make_rule("r-1"))
    checks = await eng.evaluate_entity("ent-1")
    assert len(checks[0].check_id) == 36  # UUID format


@pytest.mark.asyncio
async def test_evaluate_entity_multiple_rules(engine):
    eng, rule_store, _ = engine
    await rule_store.save_rule(_make_rule("r-1", logic="aml_threshold"))
    await rule_store.save_rule(
        _make_rule("r-2", rule_type=RuleType.SANCTIONS, logic="sanctions_hit")
    )
    checks = await eng.evaluate_entity("ent-1")
    assert len(checks) == 2
    statuses = {c.rule_id: c.status for c in checks}
    assert statuses["r-1"] == CheckStatus.PASS
    assert statuses["r-2"] == CheckStatus.FAIL


@pytest.mark.asyncio
async def test_get_rules_all(engine):
    eng, rule_store, _ = engine
    await rule_store.save_rule(_make_rule("r-1", rule_type=RuleType.AML))
    await rule_store.save_rule(_make_rule("r-2", rule_type=RuleType.KYC))
    rules = await eng.get_rules()
    assert len(rules) == 2


@pytest.mark.asyncio
async def test_get_rules_filtered_by_type(engine):
    eng, rule_store, _ = engine
    await rule_store.save_rule(_make_rule("r-1", rule_type=RuleType.AML))
    await rule_store.save_rule(_make_rule("r-2", rule_type=RuleType.KYC))
    rules = await eng.get_rules(RuleType.AML)
    assert len(rules) == 1
    assert rules[0].rule_id == "r-1"


@pytest.mark.asyncio
async def test_get_rules_returns_only_active(engine):
    eng, rule_store, _ = engine
    await rule_store.save_rule(_make_rule("r-active"))
    await rule_store.save_rule(_make_rule("r-inactive", is_active=False))
    rules = await eng.get_rules()
    assert len(rules) == 1


@pytest.mark.asyncio
async def test_register_rule(engine):
    eng, rule_store, _ = engine
    rule = _make_rule("r-new")
    result = await eng.register_rule(rule)
    assert result.rule_id == "r-new"
    fetched = await rule_store.get_rule("r-new")
    assert fetched is not None


@pytest.mark.asyncio
async def test_register_rule_persists(engine):
    eng, _, _ = engine
    rule = _make_rule("r-persist")
    await eng.register_rule(rule)
    rules = await eng.get_rules()
    assert any(r.rule_id == "r-persist" for r in rules)


@pytest.mark.asyncio
async def test_evaluate_entity_rule_id_in_check(engine):
    eng, rule_store, _ = engine
    await rule_store.save_rule(_make_rule("rule-specific"))
    checks = await eng.evaluate_entity("ent-1")
    assert checks[0].rule_id == "rule-specific"


@pytest.mark.asyncio
async def test_evaluate_entity_checked_by_system(engine):
    eng, rule_store, _ = engine
    await rule_store.save_rule(_make_rule("r-1"))
    checks = await eng.evaluate_entity("ent-1")
    assert checks[0].checked_by == "system"
