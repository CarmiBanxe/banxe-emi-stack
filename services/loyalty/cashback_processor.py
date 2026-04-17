"""
services/loyalty/cashback_processor.py — MCC-based cashback calculation
IL-LRE-01 | Phase 29 | banxe-emi-stack

Calculates and processes cashback based on MCC codes. Converts cashback to loyalty points.
Rate: 100 points per £1 cashback. All amounts Decimal (I-01).
FCA: PS22/9 (Consumer Duty — cashback must represent fair value).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
import uuid

from services.loyalty.models import (
    InMemoryPointsBalanceStore,
    InMemoryPointsTransactionStore,
    PointsBalance,
    PointsBalanceStorePort,
    PointsTransaction,
    PointsTransactionStorePort,
    PointsTransactionType,
    RewardTier,
)

MCC_RATES: dict[str, Decimal] = {
    "5411": Decimal("0.02"),  # Grocery stores — 2%
    "5812": Decimal("0.03"),  # Eating places/restaurants — 3%
    "5541": Decimal("0.01"),  # Service stations/fuel — 1%
    "5912": Decimal("0.02"),  # Drug stores/pharmacies — 2%
    "5311": Decimal("0.015"),  # Department stores — 1.5%
    "4111": Decimal("0.01"),  # Transport — 1%
    "default": Decimal("0.005"),  # Default rate — 0.5%
}

_POINTS_PER_GBP_CASHBACK = Decimal("100")


class CashbackProcessor:
    """MCC-based cashback calculation and points conversion."""

    def __init__(
        self,
        balance_store: PointsBalanceStorePort | None = None,
        tx_store: PointsTransactionStorePort | None = None,
    ) -> None:
        self._balance_store = balance_store or InMemoryPointsBalanceStore()
        self._tx_store = tx_store or InMemoryPointsTransactionStore()

    def calculate_cashback(
        self,
        customer_id: str,
        spend_amount_str: str,
        mcc: str = "default",
    ) -> dict:
        """Calculate cashback amount — pure calculation, no side effects.

        Returns {"cashback_amount": str, "rate": str, "mcc": str}.
        """
        rate = MCC_RATES.get(mcc, MCC_RATES["default"])
        spend = Decimal(spend_amount_str)
        cashback = (spend * rate).quantize(Decimal("0.01"))
        return {
            "cashback_amount": str(cashback),
            "rate": str(rate),
            "mcc": mcc,
        }

    def process_cashback(
        self,
        customer_id: str,
        spend_amount_str: str,
        mcc: str = "default",
        reference_id: str = "",
    ) -> dict:
        """Calculate cashback, convert to points, and update customer balance.

        Returns {"cashback_amount": str, "points_earned": str, "new_balance": str}.
        """
        calc = self.calculate_cashback(customer_id, spend_amount_str, mcc)
        cashback = Decimal(calc["cashback_amount"])
        points_earned = (cashback * _POINTS_PER_GBP_CASHBACK).quantize(Decimal("1"))

        now = datetime.now(UTC)
        balance = self._balance_store.get(customer_id)
        if balance is None:
            balance = PointsBalance(
                balance_id=str(uuid.uuid4()),
                customer_id=customer_id,
                tier=RewardTier.BRONZE,
                total_points=Decimal("0"),
                pending_points=Decimal("0"),
                lifetime_points=Decimal("0"),
                updated_at=now,
            )
            self._balance_store.save(balance)

        new_total = balance.total_points + points_earned
        new_lifetime = balance.lifetime_points + points_earned

        tx = PointsTransaction(
            tx_id=str(uuid.uuid4()),
            customer_id=customer_id,
            tx_type=PointsTransactionType.EARN,
            points=points_earned,
            balance_after=new_total,
            reference_id=reference_id,
            description=f"Cashback: MCC={mcc}, spend={spend_amount_str}, rate={calc['rate']}",
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
            "cashback_amount": calc["cashback_amount"],
            "points_earned": str(points_earned),
            "new_balance": str(new_total),
        }

    def list_mcc_rates(self) -> dict:
        """Return all configured MCC cashback rates."""
        return {"rates": [{"mcc": mcc, "rate": str(rate)} for mcc, rate in MCC_RATES.items()]}
