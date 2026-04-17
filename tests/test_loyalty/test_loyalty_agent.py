"""
tests/test_loyalty/test_loyalty_agent.py — Unit tests for LoyaltyAgent facade
IL-LRE-01 | Phase 29 | banxe-emi-stack
"""

from __future__ import annotations

import pytest

from services.loyalty.loyalty_agent import LoyaltyAgent


@pytest.fixture()
def agent() -> LoyaltyAgent:
    return LoyaltyAgent()


# ── get_balance ────────────────────────────────────────────────────────────


def test_get_balance_new_customer_returns_zero(agent: LoyaltyAgent) -> None:
    result = agent.get_balance("cust-1")
    assert result["total_points"] == "0"


def test_get_balance_has_required_keys(agent: LoyaltyAgent) -> None:
    result = agent.get_balance("cust-2")
    assert "customer_id" in result
    assert "tier" in result
    assert "total_points" in result
    assert "lifetime_points" in result


# ── earn_points ────────────────────────────────────────────────────────────


def test_earn_points_bronze_card_spend(agent: LoyaltyAgent) -> None:
    result = agent.earn_points("cust-3", "BRONZE", "CARD_SPEND", "100.00")
    assert result["points_earned"] == "100"


def test_earn_points_updates_balance(agent: LoyaltyAgent) -> None:
    agent.earn_points("cust-4", "BRONZE", "CARD_SPEND", "50.00")
    balance = agent.get_balance("cust-4")
    assert balance["total_points"] == "50"


def test_earn_points_silver_applies_multiplier(agent: LoyaltyAgent) -> None:
    result = agent.earn_points("cust-5", "SILVER", "CARD_SPEND", "100.00")
    assert result["points_earned"] == "150"


# ── apply_bonus ────────────────────────────────────────────────────────────


def test_apply_bonus_under_threshold(agent: LoyaltyAgent) -> None:
    result = agent.apply_bonus("cust-6", "500", "welcome bonus")
    assert result["points_added"] == "500"


def test_apply_bonus_over_threshold_returns_hitl(agent: LoyaltyAgent) -> None:
    result = agent.apply_bonus("cust-7", "99999", "large bonus")
    assert result["status"] == "HITL_REQUIRED"


# ── get_earn_history ───────────────────────────────────────────────────────


def test_get_earn_history_empty_new_customer(agent: LoyaltyAgent) -> None:
    result = agent.get_earn_history("hist-cust")
    assert result["transactions"] == []


def test_get_earn_history_after_earning(agent: LoyaltyAgent) -> None:
    agent.earn_points("hist-cust-2", "BRONZE", "CARD_SPEND", "100.00")
    result = agent.get_earn_history("hist-cust-2")
    assert len(result["transactions"]) == 1


def test_get_earn_history_with_limit(agent: LoyaltyAgent) -> None:
    for i in range(5):
        agent.earn_points(f"hist-multi-{i}", "BRONZE", "CARD_SPEND", "10.00")
    result = agent.get_earn_history("hist-multi-0", limit=2)
    assert len(result["transactions"]) <= 2


# ── redeem_points ──────────────────────────────────────────────────────────


def test_redeem_points_insufficient_balance_raises(agent: LoyaltyAgent) -> None:
    with pytest.raises(ValueError):
        agent.redeem_points("broke-cust", "opt-cashback")


def test_redeem_points_success_after_earning(agent: LoyaltyAgent) -> None:
    agent.earn_points("redeem-cust", "PLATINUM", "CARD_SPEND", "500.00")
    # PLATINUM: 3 * 3.0 * 500 = 4500 points → can redeem cashback (1000)
    result = agent.redeem_points("redeem-cust", "opt-cashback")
    assert result["redeemed_points"] == "1000"


# ── list_redeem_options ────────────────────────────────────────────────────


def test_list_redeem_options_returns_options(agent: LoyaltyAgent) -> None:
    result = agent.list_redeem_options("opts-cust")
    assert len(result["options"]) == 4


def test_list_redeem_options_has_can_afford_flag(agent: LoyaltyAgent) -> None:
    result = agent.list_redeem_options("opts-cust-2")
    for opt in result["options"]:
        assert "can_afford" in opt


# ── evaluate_tier ──────────────────────────────────────────────────────────


def test_evaluate_tier_new_customer_bronze(agent: LoyaltyAgent) -> None:
    result = agent.evaluate_tier("tier-cust")
    assert result["new_tier"] == "BRONZE"


def test_evaluate_tier_after_silver_threshold(agent: LoyaltyAgent) -> None:
    # SILVER needs 1000 lifetime points
    # BRONZE CARD_SPEND: 1pt * 1.0 * £1000 = 1000 points
    agent.earn_points("tier-upgrade-cust", "BRONZE", "CARD_SPEND", "1000.00")
    result = agent.evaluate_tier("tier-upgrade-cust")
    assert result["new_tier"] == "SILVER"
    assert result["upgraded"] is True


# ── get_tier_benefits ──────────────────────────────────────────────────────


def test_get_tier_benefits_bronze(agent: LoyaltyAgent) -> None:
    result = agent.get_tier_benefits("BRONZE")
    assert "benefits" in result


def test_get_tier_benefits_platinum(agent: LoyaltyAgent) -> None:
    result = agent.get_tier_benefits("PLATINUM")
    assert result["benefits"]["priority_support"] is True


# ── list_tiers ─────────────────────────────────────────────────────────────


def test_list_tiers_returns_4_tiers(agent: LoyaltyAgent) -> None:
    result = agent.list_tiers()
    assert len(result["tiers"]) == 4


# ── process_cashback ───────────────────────────────────────────────────────


def test_process_cashback_grocery(agent: LoyaltyAgent) -> None:
    result = agent.process_cashback("cb-cust", "100.00", mcc="5411")
    assert result["cashback_amount"] == "2.00"
    assert result["points_earned"] == "200"


def test_process_cashback_default_mcc(agent: LoyaltyAgent) -> None:
    result = agent.process_cashback("cb-cust-2", "100.00")
    assert result["points_earned"] == "50"


# ── get_expiry_forecast ────────────────────────────────────────────────────


def test_get_expiry_forecast_empty_new_customer(agent: LoyaltyAgent) -> None:
    result = agent.get_expiry_forecast("exp-cust")
    assert result["expiring_transactions"] == []
    assert result["total_expiring_points"] == "0"


def test_get_expiry_forecast_returns_correct_customer(agent: LoyaltyAgent) -> None:
    result = agent.get_expiry_forecast("exp-cust-2")
    assert result["customer_id"] == "exp-cust-2"
