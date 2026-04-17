"""
tests/test_loyalty/test_points_engine.py — Unit tests for PointsEngine
IL-LRE-01 | Phase 29 | banxe-emi-stack
"""

from __future__ import annotations

import pytest

from services.loyalty.points_engine import PointsEngine


@pytest.fixture()
def engine() -> PointsEngine:
    return PointsEngine()


# ── earn_points — CARD_SPEND ───────────────────────────────────────────────


def test_earn_bronze_card_spend_100(engine: PointsEngine) -> None:
    result = engine.earn_points("cust-1", "BRONZE", "CARD_SPEND", "100.00")
    assert result["points_earned"] == "100"


def test_earn_silver_card_spend_100_applies_multiplier(engine: PointsEngine) -> None:
    # SILVER: 1pt * 1.5 multiplier * £100 = 150 points
    result = engine.earn_points("cust-2", "SILVER", "CARD_SPEND", "100.00")
    assert result["points_earned"] == "150"


def test_earn_gold_card_spend_100(engine: PointsEngine) -> None:
    # GOLD: 2pts * 2.0 multiplier * £100 = 400 points
    result = engine.earn_points("cust-3", "GOLD", "CARD_SPEND", "100.00")
    assert result["points_earned"] == "400"


def test_earn_platinum_card_spend_100(engine: PointsEngine) -> None:
    # PLATINUM: 3pts * 3.0 multiplier * £100 = 900 points
    result = engine.earn_points("cust-4", "PLATINUM", "CARD_SPEND", "100.00")
    assert result["points_earned"] == "900"


def test_earn_gold_fx_rule(engine: PointsEngine) -> None:
    # GOLD FX: 3pts * 3.0 multiplier * £100 = 900
    result = engine.earn_points("cust-5", "GOLD", "FX", "100.00")
    assert result["points_earned"] == "900"


def test_earn_bronze_direct_debit(engine: PointsEngine) -> None:
    # BRONZE DD: 1pt * 1.0 * £50 = 50 points
    result = engine.earn_points("cust-6", "BRONZE", "DIRECT_DEBIT", "50.00")
    assert result["points_earned"] == "50"


def test_earn_returns_tier_in_result(engine: PointsEngine) -> None:
    result = engine.earn_points("cust-7", "SILVER", "CARD_SPEND", "10.00")
    assert result["tier"] == "SILVER"


def test_earn_returns_new_balance(engine: PointsEngine) -> None:
    result = engine.earn_points("cust-8", "BRONZE", "CARD_SPEND", "100.00")
    assert result["new_balance"] == "100"


def test_earn_accumulates_balance(engine: PointsEngine) -> None:
    engine.earn_points("cust-acc", "BRONZE", "CARD_SPEND", "100.00")
    result = engine.earn_points("cust-acc", "BRONZE", "CARD_SPEND", "100.00")
    assert result["new_balance"] == "200"


def test_earn_unknown_rule_raises_value_error(engine: PointsEngine) -> None:
    with pytest.raises(ValueError, match="No earn rule"):
        engine.earn_points("cust-9", "SILVER", "FX", "100.00")  # FX only for GOLD


def test_earn_invalid_tier_raises_value_error(engine: PointsEngine) -> None:
    with pytest.raises(ValueError):
        engine.earn_points("cust-10", "DIAMOND", "CARD_SPEND", "100.00")


# ── get_balance ────────────────────────────────────────────────────────────


def test_get_balance_new_customer_returns_zero(engine: PointsEngine) -> None:
    result = engine.get_balance("new-cust-1")
    assert result["total_points"] == "0"
    assert result["lifetime_points"] == "0"


def test_get_balance_returns_customer_id(engine: PointsEngine) -> None:
    result = engine.get_balance("new-cust-2")
    assert result["customer_id"] == "new-cust-2"


def test_get_balance_after_earning(engine: PointsEngine) -> None:
    engine.earn_points("bal-cust-1", "BRONZE", "CARD_SPEND", "200.00")
    result = engine.get_balance("bal-cust-1")
    assert result["total_points"] == "200"
    assert result["lifetime_points"] == "200"


def test_get_balance_has_tier_field(engine: PointsEngine) -> None:
    result = engine.get_balance("new-cust-3")
    assert "tier" in result


# ── apply_bonus ────────────────────────────────────────────────────────────


def test_apply_bonus_under_threshold(engine: PointsEngine) -> None:
    result = engine.apply_bonus("bonus-cust-1", "500", "sign-up reward")
    assert result["points_added"] == "500"


def test_apply_bonus_exactly_at_threshold(engine: PointsEngine) -> None:
    # 10000 is NOT > threshold, should pass
    result = engine.apply_bonus("bonus-cust-2", "10000", "milestone")
    assert result["points_added"] == "10000"


def test_apply_bonus_over_threshold_returns_hitl(engine: PointsEngine) -> None:
    result = engine.apply_bonus("bonus-cust-3", "10001", "large bonus")
    assert result["status"] == "HITL_REQUIRED"


def test_apply_bonus_hitl_includes_points(engine: PointsEngine) -> None:
    result = engine.apply_bonus("bonus-cust-4", "50000", "massive bonus")
    assert result["points"] == "50000"


def test_apply_bonus_updates_balance(engine: PointsEngine) -> None:
    engine.apply_bonus("bonus-cust-5", "200", "bonus")
    balance = engine.get_balance("bonus-cust-5")
    assert balance["total_points"] == "200"


def test_apply_bonus_accumulates_with_earned(engine: PointsEngine) -> None:
    engine.earn_points("bonus-acc", "BRONZE", "CARD_SPEND", "100.00")
    engine.apply_bonus("bonus-acc", "50", "extra")
    balance = engine.get_balance("bonus-acc")
    assert balance["total_points"] == "150"


# ── get_transaction_history ────────────────────────────────────────────────


def test_transaction_history_empty_for_new_customer(engine: PointsEngine) -> None:
    result = engine.get_transaction_history("hist-cust-1")
    assert result["transactions"] == []


def test_transaction_history_after_earn(engine: PointsEngine) -> None:
    engine.earn_points("hist-cust-2", "BRONZE", "CARD_SPEND", "100.00")
    result = engine.get_transaction_history("hist-cust-2")
    assert len(result["transactions"]) == 1
    assert result["transactions"][0]["tx_type"] == "EARN"


def test_transaction_history_earn_has_expires_at(engine: PointsEngine) -> None:
    engine.earn_points("hist-cust-3", "BRONZE", "CARD_SPEND", "100.00")
    result = engine.get_transaction_history("hist-cust-3")
    assert result["transactions"][0]["expires_at"] is not None


def test_transaction_history_returns_customer_id(engine: PointsEngine) -> None:
    result = engine.get_transaction_history("hist-cust-4")
    assert result["customer_id"] == "hist-cust-4"


def test_earn_updates_lifetime_points(engine: PointsEngine) -> None:
    engine.earn_points("lt-cust-1", "GOLD", "CARD_SPEND", "50.00")
    balance = engine.get_balance("lt-cust-1")
    # GOLD: 2 * 50 * 2.0 = 200
    assert balance["lifetime_points"] == "200"
