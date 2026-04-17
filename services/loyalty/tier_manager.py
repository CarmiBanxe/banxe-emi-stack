"""
services/loyalty/tier_manager.py — Tier evaluation and benefits mapping
IL-LRE-01 | Phase 29 | banxe-emi-stack

Evaluates customer tier based on lifetime points. Handles upgrades and downgrades.
Tier thresholds: BRONZE=0, SILVER=1000, GOLD=5000, PLATINUM=20000 lifetime points.
FCA: PS22/9 (fair value — benefits must be proportional).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

from services.loyalty.models import (
    InMemoryPointsBalanceStore,
    PointsBalanceStorePort,
    RewardTier,
)

TIER_THRESHOLDS: dict[RewardTier, Decimal] = {
    RewardTier.BRONZE: Decimal("0"),
    RewardTier.SILVER: Decimal("1000"),
    RewardTier.GOLD: Decimal("5000"),
    RewardTier.PLATINUM: Decimal("20000"),
}

TIER_BENEFITS: dict[RewardTier, dict] = {
    RewardTier.BRONZE: {
        "points_multiplier": "1.0",
        "fx_discount_pct": "0.00",
        "card_fee_waiver_months": 0,
        "priority_support": False,
        "earn_rate": "1 point per £1",
    },
    RewardTier.SILVER: {
        "points_multiplier": "1.5",
        "fx_discount_pct": "0.10",
        "card_fee_waiver_months": 1,
        "priority_support": False,
        "earn_rate": "1.5 points per £1",
    },
    RewardTier.GOLD: {
        "points_multiplier": "2.0",
        "fx_discount_pct": "0.25",
        "card_fee_waiver_months": 3,
        "priority_support": True,
        "earn_rate": "2 points per £1",
    },
    RewardTier.PLATINUM: {
        "points_multiplier": "3.0",
        "fx_discount_pct": "0.50",
        "card_fee_waiver_months": 12,
        "priority_support": True,
        "earn_rate": "3 points per £1",
    },
}


class TierManager:
    """Tier evaluation, upgrade/downgrade logic, and benefits mapping."""

    def __init__(self, balance_store: PointsBalanceStorePort | None = None) -> None:
        self._balance_store = balance_store or InMemoryPointsBalanceStore()

    def _determine_tier(self, lifetime_points: Decimal) -> RewardTier:
        """Determine tier from lifetime points — highest qualifying tier wins."""
        result = RewardTier.BRONZE
        for tier, threshold in TIER_THRESHOLDS.items():
            if lifetime_points >= threshold:
                result = tier
        return result

    def evaluate_tier(self, customer_id: str) -> dict:
        """Evaluate and apply tier upgrade/downgrade based on lifetime points.

        Returns {"customer_id", "old_tier", "new_tier", "lifetime_points": str, "upgraded": bool}.
        """
        balance = self._balance_store.get(customer_id)
        if balance is None:
            return {
                "customer_id": customer_id,
                "old_tier": RewardTier.BRONZE.value,
                "new_tier": RewardTier.BRONZE.value,
                "lifetime_points": "0",
                "upgraded": False,
            }

        old_tier = balance.tier
        new_tier = self._determine_tier(balance.lifetime_points)
        changed = new_tier != old_tier

        if changed:
            updated = replace(balance, tier=new_tier, updated_at=datetime.now(UTC))
            self._balance_store.update(updated)

        return {
            "customer_id": customer_id,
            "old_tier": old_tier.value,
            "new_tier": new_tier.value,
            "lifetime_points": str(balance.lifetime_points),
            "upgraded": changed,
        }

    def get_tier_benefits(self, tier_str: str) -> dict:
        """Return benefits dict for a given tier string."""
        tier = RewardTier(tier_str)
        return {
            "tier": tier_str,
            "threshold_lifetime_points": str(TIER_THRESHOLDS[tier]),
            "benefits": TIER_BENEFITS[tier],
        }

    def list_tiers(self) -> dict:
        """List all tiers with thresholds and benefits."""
        return {
            "tiers": [
                {
                    "tier": t.value,
                    "threshold_lifetime_points": str(TIER_THRESHOLDS[t]),
                    "benefits": TIER_BENEFITS[t],
                }
                for t in RewardTier
            ]
        }
