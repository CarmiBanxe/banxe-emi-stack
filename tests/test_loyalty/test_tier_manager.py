"""
tests/test_loyalty/test_tier_manager.py — Unit tests for TierManager
IL-LRE-01 | Phase 29 | banxe-emi-stack
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import uuid

import pytest

from services.loyalty.models import InMemoryPointsBalanceStore, PointsBalance, RewardTier
from services.loyalty.tier_manager import TIER_THRESHOLDS, TierManager


def _make_balance(
    customer_id: str,
    tier: RewardTier,
    lifetime_points: Decimal,
) -> PointsBalance:
    return PointsBalance(
        balance_id=str(uuid.uuid4()),
        customer_id=customer_id,
        tier=tier,
        total_points=lifetime_points,
        pending_points=Decimal("0"),
        lifetime_points=lifetime_points,
        updated_at=datetime.now(UTC),
    )


@pytest.fixture()
def manager() -> TierManager:
    return TierManager()


# ── TIER_THRESHOLDS constants ──────────────────────────────────────────────


def test_bronze_threshold_is_zero() -> None:
    assert TIER_THRESHOLDS[RewardTier.BRONZE] == Decimal("0")


def test_silver_threshold_is_1000() -> None:
    assert TIER_THRESHOLDS[RewardTier.SILVER] == Decimal("1000")


def test_gold_threshold_is_5000() -> None:
    assert TIER_THRESHOLDS[RewardTier.GOLD] == Decimal("5000")


def test_platinum_threshold_is_20000() -> None:
    assert TIER_THRESHOLDS[RewardTier.PLATINUM] == Decimal("20000")


# ── evaluate_tier — new customer ───────────────────────────────────────────


def test_evaluate_tier_no_balance_returns_bronze(manager: TierManager) -> None:
    result = manager.evaluate_tier("no-balance-cust")
    assert result["new_tier"] == "BRONZE"
    assert result["upgraded"] is False


def test_evaluate_tier_no_balance_lifetime_zero(manager: TierManager) -> None:
    result = manager.evaluate_tier("no-balance-cust-2")
    assert result["lifetime_points"] == "0"


# ── evaluate_tier — upgrades ───────────────────────────────────────────────


def test_evaluate_tier_999_points_stays_bronze() -> None:
    store = InMemoryPointsBalanceStore()
    store.save(_make_balance("c1", RewardTier.BRONZE, Decimal("999")))
    mgr = TierManager(balance_store=store)
    result = mgr.evaluate_tier("c1")
    assert result["new_tier"] == "BRONZE"
    assert result["upgraded"] is False


def test_evaluate_tier_1000_points_upgrades_to_silver() -> None:
    store = InMemoryPointsBalanceStore()
    store.save(_make_balance("c2", RewardTier.BRONZE, Decimal("1000")))
    mgr = TierManager(balance_store=store)
    result = mgr.evaluate_tier("c2")
    assert result["new_tier"] == "SILVER"
    assert result["upgraded"] is True


def test_evaluate_tier_4999_stays_silver() -> None:
    store = InMemoryPointsBalanceStore()
    store.save(_make_balance("c3", RewardTier.SILVER, Decimal("4999")))
    mgr = TierManager(balance_store=store)
    result = mgr.evaluate_tier("c3")
    assert result["new_tier"] == "SILVER"
    assert result["upgraded"] is False


def test_evaluate_tier_5000_upgrades_to_gold() -> None:
    store = InMemoryPointsBalanceStore()
    store.save(_make_balance("c4", RewardTier.SILVER, Decimal("5000")))
    mgr = TierManager(balance_store=store)
    result = mgr.evaluate_tier("c4")
    assert result["new_tier"] == "GOLD"
    assert result["upgraded"] is True


def test_evaluate_tier_19999_stays_gold() -> None:
    store = InMemoryPointsBalanceStore()
    store.save(_make_balance("c5", RewardTier.GOLD, Decimal("19999")))
    mgr = TierManager(balance_store=store)
    result = mgr.evaluate_tier("c5")
    assert result["new_tier"] == "GOLD"
    assert result["upgraded"] is False


def test_evaluate_tier_20000_upgrades_to_platinum() -> None:
    store = InMemoryPointsBalanceStore()
    store.save(_make_balance("c6", RewardTier.GOLD, Decimal("20000")))
    mgr = TierManager(balance_store=store)
    result = mgr.evaluate_tier("c6")
    assert result["new_tier"] == "PLATINUM"
    assert result["upgraded"] is True


def test_evaluate_tier_already_platinum_no_change() -> None:
    store = InMemoryPointsBalanceStore()
    store.save(_make_balance("c7", RewardTier.PLATINUM, Decimal("50000")))
    mgr = TierManager(balance_store=store)
    result = mgr.evaluate_tier("c7")
    assert result["new_tier"] == "PLATINUM"
    assert result["upgraded"] is False


def test_evaluate_tier_returns_old_tier(manager: TierManager) -> None:
    store = InMemoryPointsBalanceStore()
    store.save(_make_balance("c8", RewardTier.BRONZE, Decimal("500")))
    mgr = TierManager(balance_store=store)
    result = mgr.evaluate_tier("c8")
    assert result["old_tier"] == "BRONZE"


# ── get_tier_benefits ──────────────────────────────────────────────────────


def test_get_tier_benefits_bronze_multiplier(manager: TierManager) -> None:
    result = manager.get_tier_benefits("BRONZE")
    assert result["benefits"]["points_multiplier"] == "1.0"


def test_get_tier_benefits_silver_multiplier(manager: TierManager) -> None:
    result = manager.get_tier_benefits("SILVER")
    assert result["benefits"]["points_multiplier"] == "1.5"


def test_get_tier_benefits_gold_priority_support(manager: TierManager) -> None:
    result = manager.get_tier_benefits("GOLD")
    assert result["benefits"]["priority_support"] is True


def test_get_tier_benefits_platinum_fx_discount(manager: TierManager) -> None:
    result = manager.get_tier_benefits("PLATINUM")
    assert result["benefits"]["fx_discount_pct"] == "0.50"


def test_get_tier_benefits_returns_threshold(manager: TierManager) -> None:
    result = manager.get_tier_benefits("GOLD")
    assert result["threshold_lifetime_points"] == "5000"


def test_get_tier_benefits_invalid_tier_raises(manager: TierManager) -> None:
    with pytest.raises(ValueError):
        manager.get_tier_benefits("DIAMOND")


# ── list_tiers ─────────────────────────────────────────────────────────────


def test_list_tiers_returns_4(manager: TierManager) -> None:
    result = manager.list_tiers()
    assert len(result["tiers"]) == 4


def test_list_tiers_has_all_tiers(manager: TierManager) -> None:
    result = manager.list_tiers()
    tiers = [t["tier"] for t in result["tiers"]]
    assert "BRONZE" in tiers
    assert "SILVER" in tiers
    assert "GOLD" in tiers
    assert "PLATINUM" in tiers
