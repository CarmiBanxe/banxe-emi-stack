"""
services/loyalty/points_engine.py — Points earning and balance management
IL-LRE-01 | Phase 29 | banxe-emi-stack

Core points engine: earn points from card spend, FX, direct debit, signup bonuses.
HITL gate: manual bonus adjustments >10,000 points require Compliance Officer approval (I-27).
All amounts: Decimal (I-01). API amounts: strings (I-05).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import uuid

from services.loyalty.models import (
    EarnRuleStorePort,
    EarnRuleType,
    InMemoryEarnRuleStore,
    InMemoryPointsBalanceStore,
    InMemoryPointsTransactionStore,
    PointsBalance,
    PointsBalanceStorePort,
    PointsTransaction,
    PointsTransactionStorePort,
    PointsTransactionType,
    RewardTier,
)

_HITL_BONUS_THRESHOLD = Decimal("10000")
_DEFAULT_EXPIRY_DAYS = 365


class PointsEngine:
    """Core points earning and balance management.

    Autonomy L2. L4 HITL for manual bonus >10,000 points (I-27).
    """

    def __init__(
        self,
        earn_rule_store: EarnRuleStorePort | None = None,
        balance_store: PointsBalanceStorePort | None = None,
        tx_store: PointsTransactionStorePort | None = None,
    ) -> None:
        self._earn_rule_store = earn_rule_store or InMemoryEarnRuleStore()
        self._balance_store = balance_store or InMemoryPointsBalanceStore()
        self._tx_store = tx_store or InMemoryPointsTransactionStore()

    def _get_or_create_balance(self, customer_id: str, tier: RewardTier) -> PointsBalance:
        balance = self._balance_store.get(customer_id)
        if balance is None:
            balance = PointsBalance(
                balance_id=str(uuid.uuid4()),
                customer_id=customer_id,
                tier=tier,
                total_points=Decimal("0"),
                pending_points=Decimal("0"),
                lifetime_points=Decimal("0"),
                updated_at=datetime.now(UTC),
            )
            self._balance_store.save(balance)
        return balance

    def earn_points(
        self,
        customer_id: str,
        tier_str: str,
        rule_type_str: str,
        spend_amount_str: str,
        reference_id: str = "",
    ) -> dict:
        """Earn points for a spend transaction.

        Returns {"points_earned": str, "new_balance": str, "tier": str}.
        """
        tier = RewardTier(tier_str)
        rule_type = EarnRuleType(rule_type_str)
        spend_amount = Decimal(spend_amount_str)

        rules = self._earn_rule_store.get_rules_for_tier(tier)
        matching = [r for r in rules if r.rule_type == rule_type]
        if not matching:
            # Fallback: try BRONZE rules
            bronze_rules = self._earn_rule_store.get_rules_for_tier(RewardTier.BRONZE)
            matching = [r for r in bronze_rules if r.rule_type == rule_type]
        if not matching:
            raise ValueError(f"No earn rule found for tier={tier_str} type={rule_type_str}")

        rule = matching[0]
        points_earned = (rule.points_per_unit * spend_amount * rule.multiplier).quantize(
            Decimal("1")
        )

        balance = self._get_or_create_balance(customer_id, tier)
        new_total = balance.total_points + points_earned
        new_lifetime = balance.lifetime_points + points_earned

        now = datetime.now(UTC)
        expires_at = now + timedelta(days=_DEFAULT_EXPIRY_DAYS)

        tx = PointsTransaction(
            tx_id=str(uuid.uuid4()),
            customer_id=customer_id,
            tx_type=PointsTransactionType.EARN,
            points=points_earned,
            balance_after=new_total,
            reference_id=reference_id,
            description=f"{rule_type_str} earn: {spend_amount_str}",
            created_at=now,
            expires_at=expires_at,
        )
        self._tx_store.append(tx)

        updated = replace(
            balance,
            total_points=new_total,
            lifetime_points=new_lifetime,
            updated_at=now,
        )
        self._balance_store.update(updated)

        return {
            "points_earned": str(points_earned),
            "new_balance": str(new_total),
            "tier": tier_str,
        }

    def apply_bonus(
        self,
        customer_id: str,
        points_str: str,
        reason: str,
        reference_id: str = "",
    ) -> dict:
        """Apply a bonus points adjustment.

        HITL_REQUIRED if points > 10,000 (I-27).
        Returns {"points_added": str, "new_balance": str} or {"status": "HITL_REQUIRED"}.
        """
        points = Decimal(points_str)
        if points > _HITL_BONUS_THRESHOLD:
            return {
                "status": "HITL_REQUIRED",
                "points": points_str,
                "reason": "Manual point adjustments >10,000 require Compliance Officer approval (I-27)",
            }

        balance = self._get_or_create_balance(customer_id, RewardTier.BRONZE)
        new_total = balance.total_points + points
        new_lifetime = balance.lifetime_points + points

        now = datetime.now(UTC)
        tx = PointsTransaction(
            tx_id=str(uuid.uuid4()),
            customer_id=customer_id,
            tx_type=PointsTransactionType.BONUS,
            points=points,
            balance_after=new_total,
            reference_id=reference_id,
            description=reason,
            created_at=now,
        )
        self._tx_store.append(tx)

        updated = replace(
            balance,
            total_points=new_total,
            lifetime_points=new_lifetime,
            updated_at=now,
        )
        self._balance_store.update(updated)

        return {
            "points_added": str(points),
            "new_balance": str(new_total),
        }

    def get_balance(self, customer_id: str) -> dict:
        """Get current points balance. Creates fresh balance for new customers."""
        balance = self._get_or_create_balance(customer_id, RewardTier.BRONZE)
        return {
            "customer_id": customer_id,
            "tier": balance.tier.value,
            "total_points": str(balance.total_points),
            "pending_points": str(balance.pending_points),
            "lifetime_points": str(balance.lifetime_points),
        }

    def get_transaction_history(self, customer_id: str, limit: int = 100) -> dict:
        """Get recent points transaction history for a customer."""
        txs = self._tx_store.list_by_customer(customer_id, limit=limit)
        return {
            "customer_id": customer_id,
            "transactions": [
                {
                    "tx_id": t.tx_id,
                    "tx_type": t.tx_type.value,
                    "points": str(t.points),
                    "balance_after": str(t.balance_after),
                    "description": t.description,
                    "created_at": t.created_at.isoformat(),
                    "expires_at": t.expires_at.isoformat() if t.expires_at else None,
                }
                for t in txs
            ],
        }
