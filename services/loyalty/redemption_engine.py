"""
services/loyalty/redemption_engine.py — Points redemption logic
IL-LRE-01 | Phase 29 | banxe-emi-stack

Handles points redemption: cashback, FX fee discount, card fee waiver, partner vouchers.
Validates balance sufficiency before deducting. All amounts Decimal (I-01).
FCA: PS22/9 (fair value of reward redemptions).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
import uuid

from services.loyalty.models import (
    InMemoryPointsBalanceStore,
    InMemoryPointsTransactionStore,
    InMemoryRedeemOptionStore,
    PointsBalanceStorePort,
    PointsTransaction,
    PointsTransactionStorePort,
    PointsTransactionType,
    RedeemOptionStorePort,
)


class RedemptionEngine:
    """Points redemption — cashback, discounts, waivers, vouchers."""

    def __init__(
        self,
        option_store: RedeemOptionStorePort | None = None,
        balance_store: PointsBalanceStorePort | None = None,
        tx_store: PointsTransactionStorePort | None = None,
    ) -> None:
        self._option_store = option_store or InMemoryRedeemOptionStore()
        self._balance_store = balance_store or InMemoryPointsBalanceStore()
        self._tx_store = tx_store or InMemoryPointsTransactionStore()

    def redeem(self, customer_id: str, option_id: str, quantity: int = 1) -> dict:
        """Redeem points for a reward.

        Raises:
            ValueError: option not found, not active, or insufficient balance
        """
        option = self._option_store.get(option_id)
        if option is None:
            raise ValueError(f"Redeem option not found: {option_id}")
        if not option.active:
            raise ValueError(f"Redeem option is not active: {option_id}")
        if quantity < 1:
            raise ValueError(f"Quantity must be >= 1, got {quantity}")

        balance = self._balance_store.get(customer_id)
        if balance is None:
            raise ValueError(f"No points balance found for customer: {customer_id}")

        required = option.points_required * Decimal(quantity)
        if balance.total_points < required:
            raise ValueError(f"Insufficient points: have {balance.total_points}, need {required}")

        now = datetime.now(UTC)
        new_total = balance.total_points - required

        tx = PointsTransaction(
            tx_id=str(uuid.uuid4()),
            customer_id=customer_id,
            tx_type=PointsTransactionType.REDEEM,
            points=-required,
            balance_after=new_total,
            reference_id=option_id,
            description=f"Redeemed: {option.description} x{quantity}",
            created_at=now,
        )
        self._tx_store.append(tx)

        updated = replace(balance, total_points=new_total, updated_at=now)
        self._balance_store.update(updated)

        return {
            "redeemed_points": str(required),
            "remaining_balance": str(new_total),
            "reward": {
                "option_id": option.option_id,
                "type": option.option_type.value,
                "value": str(option.reward_value * Decimal(quantity)),
                "description": option.description,
                "quantity": quantity,
            },
        }

    def list_options(self, customer_id: str) -> dict:
        """List active redemption options with can_afford flag per customer balance."""
        balance = self._balance_store.get(customer_id)
        total = balance.total_points if balance else Decimal("0")
        options = self._option_store.list_active()
        return {
            "customer_id": customer_id,
            "current_balance": str(total),
            "options": [
                {
                    "option_id": o.option_id,
                    "type": o.option_type.value,
                    "points_required": str(o.points_required),
                    "reward_value": str(o.reward_value),
                    "description": o.description,
                    "can_afford": total >= o.points_required,
                }
                for o in options
            ],
        }

    def get_redemption_history(self, customer_id: str) -> dict:
        """List all REDEEM transactions for a customer."""
        txs = self._tx_store.list_by_customer(customer_id)
        redeemed = [t for t in txs if t.tx_type == PointsTransactionType.REDEEM]
        return {
            "customer_id": customer_id,
            "redemptions": [
                {
                    "tx_id": t.tx_id,
                    "points": str(t.points),
                    "reference_id": t.reference_id,
                    "description": t.description,
                    "created_at": t.created_at.isoformat(),
                }
                for t in redeemed
            ],
        }
