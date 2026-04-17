"""
services/loyalty/loyalty_agent.py — Loyalty & Rewards Agent facade
IL-LRE-01 | Phase 29 | banxe-emi-stack

Orchestrates all loyalty components: points engine, tier manager, redemption,
cashback, and expiry management. All components share the same InMemory stores.
Trust Zone: AMBER | Autonomy L2 | L4 HITL for manual bonus >10k (I-27).
FCA: PS22/9 (Consumer Duty — fair value of rewards), BCOBS 5 (post-sale).
"""

from __future__ import annotations

from services.loyalty.cashback_processor import CashbackProcessor
from services.loyalty.expiry_manager import ExpiryManager
from services.loyalty.models import (
    InMemoryEarnRuleStore,
    InMemoryPointsBalanceStore,
    InMemoryPointsTransactionStore,
    InMemoryRedeemOptionStore,
)
from services.loyalty.points_engine import PointsEngine
from services.loyalty.redemption_engine import RedemptionEngine
from services.loyalty.tier_manager import TierManager


class LoyaltyAgent:
    """
    Central Loyalty & Rewards orchestrator.
    Wires all loyalty components over shared InMemory stores.
    Autonomy L2. L4 HITL for manual point adjustments >10,000 (I-27).
    """

    def __init__(self) -> None:
        # Shared stores — all components operate on the same in-memory state
        self._balance_store = InMemoryPointsBalanceStore()
        self._earn_rule_store = InMemoryEarnRuleStore()
        self._option_store = InMemoryRedeemOptionStore()
        self._tx_store = InMemoryPointsTransactionStore()

        self._points_engine = PointsEngine(
            earn_rule_store=self._earn_rule_store,
            balance_store=self._balance_store,
            tx_store=self._tx_store,
        )
        self._tier_manager = TierManager(balance_store=self._balance_store)
        self._redemption_engine = RedemptionEngine(
            option_store=self._option_store,
            balance_store=self._balance_store,
            tx_store=self._tx_store,
        )
        self._cashback_processor = CashbackProcessor(
            balance_store=self._balance_store,
            tx_store=self._tx_store,
        )
        self._expiry_manager = ExpiryManager(
            tx_store=self._tx_store,
            balance_store=self._balance_store,
        )

    def get_balance(self, customer_id: str) -> dict:
        """Get current points balance and tier for a customer."""
        return self._points_engine.get_balance(customer_id)

    def earn_points(
        self,
        customer_id: str,
        tier_str: str,
        rule_type_str: str,
        spend_amount_str: str,
        reference_id: str = "",
    ) -> dict:
        """Earn points from card spend, FX, or direct debit."""
        return self._points_engine.earn_points(
            customer_id, tier_str, rule_type_str, spend_amount_str, reference_id
        )

    def apply_bonus(
        self,
        customer_id: str,
        points_str: str,
        reason: str,
        reference_id: str = "",
    ) -> dict:
        """Apply a bonus. HITL_REQUIRED if >10,000 points (I-27)."""
        return self._points_engine.apply_bonus(customer_id, points_str, reason, reference_id)

    def get_earn_history(self, customer_id: str, limit: int = 100) -> dict:
        """Get transaction history for a customer."""
        return self._points_engine.get_transaction_history(customer_id, limit=limit)

    def redeem_points(
        self,
        customer_id: str,
        option_id: str,
        quantity: int = 1,
    ) -> dict:
        """Redeem points for a reward option."""
        return self._redemption_engine.redeem(customer_id, option_id, quantity)

    def list_redeem_options(self, customer_id: str) -> dict:
        """List all active redemption options with affordability flags."""
        return self._redemption_engine.list_options(customer_id)

    def evaluate_tier(self, customer_id: str) -> dict:
        """Evaluate and apply tier upgrade/downgrade based on lifetime points."""
        return self._tier_manager.evaluate_tier(customer_id)

    def get_tier_benefits(self, tier_str: str) -> dict:
        """Return benefits for a specific tier."""
        return self._tier_manager.get_tier_benefits(tier_str)

    def list_tiers(self) -> dict:
        """List all tiers with thresholds and benefits."""
        return self._tier_manager.list_tiers()

    def process_cashback(
        self,
        customer_id: str,
        spend_amount_str: str,
        mcc: str = "default",
        reference_id: str = "",
    ) -> dict:
        """Process MCC-based cashback — convert to loyalty points."""
        return self._cashback_processor.process_cashback(
            customer_id, spend_amount_str, mcc, reference_id
        )

    def get_expiry_forecast(self, customer_id: str, days_ahead: int = 30) -> dict:
        """Return points expiring in the next days_ahead days."""
        return self._expiry_manager.get_expiring_soon(customer_id, days_ahead)
