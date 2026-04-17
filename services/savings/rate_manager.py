"""
services/savings/rate_manager.py — Rate management (HITL I-27), history, tiered rates
IL-SIE-01 | Phase 31 | banxe-emi-stack
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from decimal import Decimal
import uuid

from services.savings.models import (
    InMemoryInterestRateStore,
    InMemorySavingsProductStore,
    InterestRate,
    InterestRatePort,
    SavingsProductPort,
)

_TIER_THRESHOLDS: list[tuple[Decimal, Decimal]] = [
    (Decimal("0"), Decimal("0")),
    (Decimal("10000"), Decimal("0.001")),
    (Decimal("50000"), Decimal("0.002")),
    (Decimal("100000"), Decimal("0.003")),
]


class RateManager:
    def __init__(
        self,
        rate_store: InterestRatePort | None = None,
        product_store: SavingsProductPort | None = None,
    ) -> None:
        self._rate_store = rate_store or InMemoryInterestRateStore()
        self._product_store = product_store or InMemorySavingsProductStore()

    def set_rate(
        self, product_id: str, gross_rate: Decimal, _effective_from: datetime | None = None
    ) -> dict[str, str]:
        """Rate changes always require HITL (I-27, FCA BCOBS 5)."""
        return {
            "status": "HITL_REQUIRED",
            "product_id": product_id,
            "proposed_rate": str(gross_rate),
            "reason": "rate_change_requires_human_approval",
        }

    def apply_rate_change(
        self,
        product_id: str,
        gross_rate: Decimal,
        aer: Decimal,
        effective_from: datetime | None = None,
    ) -> dict[str, str]:
        """Apply approved rate change — called after HITL approval."""
        now = datetime.now(UTC)
        eff = effective_from or now
        current = self._rate_store.get_current(product_id)
        if current is not None:
            self._rate_store.save(dataclasses.replace(current, effective_to=eff))
        rate = InterestRate(
            rate_id=str(uuid.uuid4()),
            product_id=product_id,
            gross_rate=gross_rate,
            aer=aer,
            effective_from=eff,
            effective_to=None,
            created_at=now,
        )
        self._rate_store.save(rate)
        return {
            "rate_id": rate.rate_id,
            "product_id": product_id,
            "gross_rate": str(gross_rate),
            "aer": str(aer),
            "effective_from": eff.isoformat(),
        }

    def get_current_rate(self, product_id: str) -> dict[str, str]:
        product = self._product_store.get(product_id)
        if product is None:
            raise ValueError(f"Product not found: {product_id}")
        rate = self._rate_store.get_current(product_id)
        gross = rate.gross_rate if rate else product.gross_rate
        aer = rate.aer if rate else product.aer
        return {
            "product_id": product_id,
            "gross_rate": str(gross),
            "aer": str(aer),
            "source": "rate_store" if rate else "product_default",
        }

    def get_rate_history(self, product_id: str) -> dict[str, object]:
        history = self._rate_store.list_history(product_id)
        return {
            "product_id": product_id,
            "rates": [
                {
                    "rate_id": r.rate_id,
                    "gross_rate": str(r.gross_rate),
                    "aer": str(r.aer),
                    "effective_from": r.effective_from.isoformat(),
                    "effective_to": r.effective_to.isoformat() if r.effective_to else None,
                }
                for r in history
            ],
            "count": len(history),
        }

    def get_tiered_rate(self, product_id: str, balance: Decimal) -> dict[str, str]:
        """Returns base rate + balance-band bonus."""
        current = self.get_current_rate(product_id)
        base = Decimal(current["gross_rate"])
        bonus = Decimal("0")
        for threshold, band_bonus in _TIER_THRESHOLDS:
            if balance >= threshold:
                bonus = band_bonus
        return {
            "product_id": product_id,
            "base_rate": str(base),
            "balance_bonus": str(bonus),
            "effective_rate": str(base + bonus),
            "balance": str(balance),
        }
