"""
services/treasury/funding_optimizer.py
IL-TLM-01 | Phase 17

Optimal fund allocation: minimize idle cash, maximize CASS 15 compliance.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from services.treasury.models import LiquidityStorePort, TreasuryAuditPort

_SURPLUS_THRESHOLD_RATIO = Decimal("0.10")  # 10% above required_min triggers SWEEP_OUT
_IDLE_BUFFER_RATIO = Decimal("0.10")  # 10% buffer above required_min is reserved


@dataclass(frozen=True)
class AllocationRecommendation:
    """Recommendation produced by FundingOptimizer."""

    pool_id: str
    action: str  # "HOLD", "SWEEP_OUT", "DRAW_DOWN"
    amount: Decimal
    funding_source_id: str | None
    rationale: str


class FundingOptimizer:
    """Optimize fund allocation across liquidity pools.

    Recommends SWEEP_OUT when surplus > 10% of required_minimum,
    DRAW_DOWN when balance < required_minimum, otherwise HOLD.
    """

    def __init__(self, store: LiquidityStorePort, audit: TreasuryAuditPort) -> None:
        self._store = store
        self._audit = audit

    async def optimize(
        self,
        pool_ids: list[str],
        actor: str,
    ) -> list[AllocationRecommendation]:
        """Generate allocation recommendations for listed pools."""
        recommendations: list[AllocationRecommendation] = []

        for pool_id in pool_ids:
            pool = await self._store.get_pool(pool_id)
            if pool is None:
                continue

            surplus_threshold = pool.required_minimum * _SURPLUS_THRESHOLD_RATIO
            surplus = pool.current_balance - pool.required_minimum

            if pool.current_balance < pool.required_minimum:
                shortfall = pool.required_minimum - pool.current_balance
                rec = AllocationRecommendation(
                    pool_id=pool_id,
                    action="DRAW_DOWN",
                    amount=shortfall,
                    funding_source_id=None,
                    rationale=(
                        f"Balance {pool.current_balance} below required minimum "
                        f"{pool.required_minimum}; draw down {shortfall} to restore compliance."
                    ),
                )
            elif surplus > surplus_threshold:
                sweep_amount = surplus - surplus_threshold
                rec = AllocationRecommendation(
                    pool_id=pool_id,
                    action="SWEEP_OUT",
                    amount=sweep_amount,
                    funding_source_id=None,
                    rationale=(
                        f"Surplus {surplus} exceeds 10% buffer threshold {surplus_threshold}; "
                        f"sweep {sweep_amount} to optimize idle cash."
                    ),
                )
            else:
                rec = AllocationRecommendation(
                    pool_id=pool_id,
                    action="HOLD",
                    amount=Decimal("0"),
                    funding_source_id=None,
                    rationale=(
                        f"Balance {pool.current_balance} within acceptable range "
                        f"(required={pool.required_minimum}). No action required."
                    ),
                )

            recommendations.append(rec)

        await self._audit.log(
            event_type="optimizer.recommendations_generated",
            entity_id="optimizer",
            details={
                "pool_ids": pool_ids,
                "recommendation_count": len(recommendations),
            },
            actor=actor,
        )
        return recommendations

    async def get_idle_cash(self, pool_id: str) -> Decimal:
        """Return idle cash: balance minus required_minimum minus 10% buffer."""
        pool = await self._store.get_pool(pool_id)
        if pool is None:
            raise ValueError(f"Pool {pool_id!r} not found")
        buffer = pool.required_minimum * _IDLE_BUFFER_RATIO
        idle = pool.current_balance - pool.required_minimum - buffer
        return max(Decimal("0"), idle)
