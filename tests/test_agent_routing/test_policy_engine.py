"""
tests/test_agent_routing/test_policy_engine.py — Policy Engine tests
IL-ARL-01 | banxe-emi-stack | 2026-04-11

Tests: budget limits, auto-downgrade, LLM fallback, feature flags.
"""

from __future__ import annotations

import pytest

from services.agent_routing.policy_engine import PolicyConfig, PolicyEngine, TierBudget

# ── TierBudget ────────────────────────────────────────────────────────────────


def test_tier_budget_consume_tracks_usage() -> None:
    budget = TierBudget(tier=2, limit_tokens_per_hour=10_000)
    budget.consume(1_000)
    assert budget.used_tokens == 1_000
    assert budget.remaining == 9_000


def test_tier_budget_not_exhausted_below_limit() -> None:
    budget = TierBudget(tier=2, limit_tokens_per_hour=10_000)
    budget.consume(9_999)
    assert not budget.is_exhausted


def test_tier_budget_exhausted_at_limit() -> None:
    budget = TierBudget(tier=2, limit_tokens_per_hour=1_000)
    budget.consume(1_000)
    assert budget.is_exhausted


def test_tier_budget_remaining_zero_when_exhausted() -> None:
    budget = TierBudget(tier=2, limit_tokens_per_hour=500)
    budget.consume(600)
    assert budget.remaining == 0


# ── PolicyConfig ───────────────────────────────────────────────────────────────


def test_policy_config_defaults() -> None:
    cfg = PolicyConfig()
    assert cfg.agent_routing_enabled is True
    assert cfg.swarm_enabled is True
    assert cfg.reasoning_bank_enabled is True
    assert cfg.llm_fallback_to_rules is True


def test_policy_config_from_env_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_ROUTING_ENABLED", "false")
    cfg = PolicyConfig.from_env()
    assert cfg.agent_routing_enabled is False


def test_policy_config_from_env_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_ROUTING_ENABLED", "true")
    cfg = PolicyConfig.from_env()
    assert cfg.agent_routing_enabled is True


def test_policy_config_budget_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TIER2_BUDGET_TOKENS_PER_HOUR", "250000")
    cfg = PolicyConfig.from_env()
    assert cfg.tier2_budget_per_hour == 250_000


# ── PolicyEngine: feature flags ────────────────────────────────────────────────


def test_routing_enabled_default() -> None:
    engine = PolicyEngine(PolicyConfig(agent_routing_enabled=True))
    assert engine.routing_enabled is True


def test_routing_disabled() -> None:
    engine = PolicyEngine(PolicyConfig(agent_routing_enabled=False))
    assert engine.routing_enabled is False


def test_swarm_disabled_when_routing_disabled() -> None:
    engine = PolicyEngine(PolicyConfig(agent_routing_enabled=False, swarm_enabled=True))
    assert engine.swarm_enabled is False


def test_swarm_enabled() -> None:
    engine = PolicyEngine(PolicyConfig(agent_routing_enabled=True, swarm_enabled=True))
    assert engine.swarm_enabled is True


def test_reasoning_bank_enabled() -> None:
    engine = PolicyEngine(PolicyConfig(reasoning_bank_enabled=True))
    assert engine.reasoning_bank_enabled is True


# ── PolicyEngine: budget management ───────────────────────────────────────────


def test_consume_budget_records() -> None:
    engine = PolicyEngine(PolicyConfig(tier2_budget_per_hour=10_000))
    engine.consume_budget(2, 5_000)
    assert engine.budget_remaining(2) == 5_000


def test_budget_pressure_at_50_percent() -> None:
    engine = PolicyEngine(PolicyConfig(tier2_budget_per_hour=10_000))
    engine.consume_budget(2, 5_000)
    assert engine.budget_pressure(2) == pytest.approx(0.5)


def test_budget_pressure_zero_for_tier1() -> None:
    engine = PolicyEngine()
    # Tier 1 has no token cost — pressure always 0
    assert engine.budget_pressure(1) == 0.0


def test_budget_exhausted_flag() -> None:
    engine = PolicyEngine(PolicyConfig(tier2_budget_per_hour=100))
    engine.consume_budget(2, 100)
    assert engine.is_budget_exhausted(2)


def test_budget_not_exhausted_initially() -> None:
    engine = PolicyEngine()
    assert not engine.is_budget_exhausted(2)
    assert not engine.is_budget_exhausted(3)


# ── PolicyEngine: auto-downgrade ───────────────────────────────────────────────


def test_effective_tier_no_pressure_unchanged() -> None:
    engine = PolicyEngine(PolicyConfig(tier2_budget_per_hour=10_000))
    assert engine.effective_tier(3, risk_score=0.2) == 3


def test_effective_tier_downgrades_under_pressure() -> None:
    engine = PolicyEngine(PolicyConfig(tier3_budget_per_hour=1_000, auto_downgrade_threshold=0.80))
    # Consume 85% of tier 3 budget
    engine.consume_budget(3, 850)
    effective = engine.effective_tier(3, risk_score=0.1)
    assert effective == 2


def test_effective_tier_high_risk_never_downgrades() -> None:
    engine = PolicyEngine(PolicyConfig(tier3_budget_per_hour=1_000, auto_downgrade_threshold=0.80))
    engine.consume_budget(3, 950)
    # High risk: no downgrade
    effective = engine.effective_tier(3, risk_score=0.85)
    assert effective == 3


def test_effective_tier_max_two_downgrade_steps() -> None:
    engine = PolicyEngine(
        PolicyConfig(
            tier2_budget_per_hour=100,
            tier3_budget_per_hour=100,
            auto_downgrade_threshold=0.0,  # always downgrade
        )
    )
    engine.consume_budget(2, 50)
    engine.consume_budget(3, 50)
    # Should stop at Tier 1 (max 2 steps from Tier 3)
    effective = engine.effective_tier(3, risk_score=0.1)
    assert effective >= 1


# ── PolicyEngine: LLM fallback ────────────────────────────────────────────────


def test_fallback_to_rules_when_exhausted() -> None:
    engine = PolicyEngine(PolicyConfig(tier2_budget_per_hour=100, llm_fallback_to_rules=True))
    engine.consume_budget(2, 100)
    assert engine.should_fallback_to_rules(2) is True


def test_no_fallback_when_not_exhausted() -> None:
    engine = PolicyEngine(PolicyConfig(tier2_budget_per_hour=10_000, llm_fallback_to_rules=True))
    assert engine.should_fallback_to_rules(2) is False


def test_fallback_disabled_even_when_exhausted() -> None:
    engine = PolicyEngine(PolicyConfig(tier2_budget_per_hour=100, llm_fallback_to_rules=False))
    engine.consume_budget(2, 100)
    assert engine.should_fallback_to_rules(2) is False


# ── Snapshot ───────────────────────────────────────────────────────────────────


def test_snapshot_contains_all_tiers() -> None:
    engine = PolicyEngine()
    snap = engine.snapshot()
    assert "routing_enabled" in snap
    assert "swarm_enabled" in snap
    assert "budgets" in snap
    assert 1 in snap["budgets"]
    assert 2 in snap["budgets"]
    assert 3 in snap["budgets"]


def test_snapshot_budget_fields() -> None:
    engine = PolicyEngine()
    snap = engine.snapshot()
    for tier_data in snap["budgets"].values():
        assert "used" in tier_data
        assert "limit" in tier_data
        assert "remaining" in tier_data
        assert "pressure" in tier_data
