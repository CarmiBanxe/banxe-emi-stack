"""
tests/test_agent_routing/test_playbook_engine.py — Playbook Engine tests
IL-ARL-01 | banxe-emi-stack | 2026-04-11

Tests: playbook loading, tier assignment, condition evaluation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from services.agent_routing.playbook_engine import (
    PlaybookEngine,
    PlaybookNotFoundError,
)

_PLAYBOOKS_DIR = Path(__file__).parent.parent.parent / "config" / "playbooks"


# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture
def engine() -> PlaybookEngine:
    return PlaybookEngine()


@pytest.fixture
def eu_sepa_ctx_tier1() -> dict:
    """Risk context that should route to Tier 1."""
    return {
        "known_beneficiary": True,
        "sanctions_hit": False,
        "device_risk": "low",
        "anomaly_count": 0,
        "amount_eur": 500,
    }


@pytest.fixture
def eu_sepa_ctx_tier2() -> dict:
    """Risk context that should route to Tier 2."""
    return {
        "known_beneficiary": False,
        "new_beneficiary": True,
        "sanctions_hit": False,
        "device_risk": "medium",
        "anomaly_count": 0,
        "amount_eur": 500,
    }


@pytest.fixture
def eu_sepa_ctx_tier3() -> dict:
    """Risk context that should route to Tier 3."""
    return {
        "sanctions_hit": True,
        "cumulative_risk_score": 0.80,
        "amount_eur": 15000,
        "cross_border": True,
    }


# ── Loading tests ──────────────────────────────────────────────────────────────


def test_engine_loads_playbooks(engine: PlaybookEngine) -> None:
    """PlaybookEngine loads playbooks from config/playbooks/."""
    assert len(engine.list_playbooks()) >= 3


def test_engine_loads_eu_sepa(engine: PlaybookEngine) -> None:
    assert "eu_sepa_retail_v1" in engine.list_playbooks()


def test_engine_loads_uk_fps(engine: PlaybookEngine) -> None:
    assert "uk_fps_retail_v1" in engine.list_playbooks()


def test_engine_loads_high_risk(engine: PlaybookEngine) -> None:
    assert "high_risk_jurisdiction_v1" in engine.list_playbooks()


def test_get_playbook_returns_dict(engine: PlaybookEngine) -> None:
    pb = engine.get_playbook("eu_sepa_retail_v1")
    assert isinstance(pb, dict)
    assert pb["product"] == "sepa_retail_transfer"


def test_get_playbook_unknown_returns_none(engine: PlaybookEngine) -> None:
    assert engine.get_playbook("nonexistent_v999") is None


def test_playbook_has_required_fields(engine: PlaybookEngine) -> None:
    pb = engine.get_playbook("eu_sepa_retail_v1")
    assert pb is not None
    for field in ("playbook_id", "product", "jurisdictions", "tiers"):
        assert field in pb, f"Missing field: {field}"


def test_find_playbook_eu(engine: PlaybookEngine) -> None:
    pb = engine.find_playbook("sepa_retail_transfer", "EU")
    assert pb is not None
    assert pb["playbook_id"] == "eu_sepa_retail_v1"


def test_find_playbook_uk(engine: PlaybookEngine) -> None:
    pb = engine.find_playbook("fps_retail_transfer", "UK")
    assert pb is not None
    assert pb["playbook_id"] == "uk_fps_retail_v1"


def test_find_playbook_unknown_returns_none(engine: PlaybookEngine) -> None:
    assert engine.find_playbook("unknown_product", "XX") is None


def test_reload_preserves_playbooks(engine: PlaybookEngine) -> None:
    engine.reload()
    assert len(engine.list_playbooks()) >= 3


# ── Tier assignment tests ──────────────────────────────────────────────────────


def test_assign_tier1_eu_sepa(engine: PlaybookEngine, eu_sepa_ctx_tier1: dict) -> None:
    tier, playbook_id = engine.assign_tier("sepa_retail_transfer", "EU", eu_sepa_ctx_tier1)
    assert tier == 1
    assert playbook_id == "eu_sepa_retail_v1"


def test_assign_tier2_eu_sepa_new_beneficiary(
    engine: PlaybookEngine, eu_sepa_ctx_tier2: dict
) -> None:
    tier, _ = engine.assign_tier("sepa_retail_transfer", "EU", eu_sepa_ctx_tier2)
    assert tier == 2


def test_assign_tier3_eu_sepa_sanctions(engine: PlaybookEngine, eu_sepa_ctx_tier3: dict) -> None:
    tier, _ = engine.assign_tier("sepa_retail_transfer", "EU", eu_sepa_ctx_tier3)
    assert tier == 3


def test_assign_tier3_eu_sepa_high_risk_score(engine: PlaybookEngine) -> None:
    ctx = {"cumulative_risk_score": 0.80}
    tier, _ = engine.assign_tier("sepa_retail_transfer", "EU", ctx)
    assert tier == 3


def test_assign_tier3_eu_sepa_large_amount(engine: PlaybookEngine) -> None:
    ctx = {"amount_eur": 15000}
    tier, _ = engine.assign_tier("sepa_retail_transfer", "EU", ctx)
    assert tier == 3


def test_assign_tier_uk_fps_tier1(engine: PlaybookEngine) -> None:
    ctx = {
        "known_beneficiary": True,
        "sanctions_hit": False,
        "device_risk": "low",
        "anomaly_count": 0,
        "customer_age_days": 120,
        "amount_eur": 400,
    }
    tier, pb_id = engine.assign_tier("fps_retail_transfer", "UK", ctx)
    assert tier == 1
    assert pb_id == "uk_fps_retail_v1"


def test_assign_tier_unknown_product_raises(engine: PlaybookEngine) -> None:
    with pytest.raises(PlaybookNotFoundError):
        engine.assign_tier("unknown_product", "EU", {})


def test_assign_tier_unknown_jurisdiction_raises(engine: PlaybookEngine) -> None:
    with pytest.raises(PlaybookNotFoundError):
        engine.assign_tier("sepa_retail_transfer", "XX", {})


# ── Condition evaluation tests ─────────────────────────────────────────────────


def test_condition_equals_true(engine: PlaybookEngine) -> None:
    result = engine._eval_condition("known_beneficiary = true", {"known_beneficiary": True})
    assert result is True


def test_condition_equals_false_not_matched(engine: PlaybookEngine) -> None:
    result = engine._eval_condition("known_beneficiary = true", {"known_beneficiary": False})
    assert result is False


def test_condition_greater_equal(engine: PlaybookEngine) -> None:
    assert engine._eval_condition("cumulative_risk_score >= 0.75", {"cumulative_risk_score": 0.80})


def test_condition_less_than(engine: PlaybookEngine) -> None:
    assert engine._eval_condition("customer_age_days < 30", {"customer_age_days": 10})


def test_condition_less_equal(engine: PlaybookEngine) -> None:
    assert engine._eval_condition("anomaly_count <= 1", {"anomaly_count": 1})


def test_condition_in_list(engine: PlaybookEngine) -> None:
    assert engine._eval_condition("device_risk in [low]", {"device_risk": "low"})


def test_condition_in_list_multi(engine: PlaybookEngine) -> None:
    assert engine._eval_condition("device_risk in [low, medium]", {"device_risk": "medium"})


def test_condition_not_in_list(engine: PlaybookEngine) -> None:
    assert not engine._eval_condition("device_risk in [low]", {"device_risk": "high"})


def test_condition_missing_key_returns_false(engine: PlaybookEngine) -> None:
    assert not engine._eval_condition("unknown_key = true", {})


# ── Invalid playbook loading ───────────────────────────────────────────────────


def test_invalid_playbook_raises(tmp_path: Path) -> None:
    bad_yaml = tmp_path / "bad_playbook.yaml"
    bad_yaml.write_text("playbook_id: test\n# missing required fields\n")
    engine = PlaybookEngine(playbooks_dir=tmp_path)
    # Should load zero playbooks gracefully (parse error is logged, not raised)
    assert len(engine.list_playbooks()) == 0


def test_not_mapping_yaml_raises(tmp_path: Path) -> None:
    bad_yaml = tmp_path / "list_playbook.yaml"
    bad_yaml.write_text("- item1\n- item2\n")
    engine = PlaybookEngine(playbooks_dir=tmp_path)
    assert len(engine.list_playbooks()) == 0


def test_nonexistent_playbooks_dir(tmp_path: Path) -> None:
    engine = PlaybookEngine(playbooks_dir=tmp_path / "nonexistent")
    assert len(engine.list_playbooks()) == 0
