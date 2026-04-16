"""
services/treasury/liquidity_monitor.py
IL-TLM-01 | Phase 17

Real-time cash position monitor (CASS 15.6 safeguarding compliance).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import uuid

from services.treasury.models import (
    CashPosition,
    LiquidityPool,
    LiquidityStorePort,
    TreasuryAuditPort,
)


class LiquidityMonitor:
    """Real-time liquidity and cash position monitor.

    Monitors pool compliance with CASS 15.3 floor (required_minimum).
    """

    def __init__(self, store: LiquidityStorePort, audit: TreasuryAuditPort) -> None:
        self._store = store
        self._audit = audit

    async def get_positions(self, pool_id: str) -> list[CashPosition]:
        """Fetch all cash positions for a pool."""
        positions = await self._store.list_positions(pool_id)
        await self._audit.log(
            event_type="liquidity.positions_fetched",
            entity_id=pool_id,
            details={"count": len(positions)},
            actor="system",
        )
        return positions

    async def add_position(
        self,
        pool_id: str,
        amount_str: str,
        currency: str,
        description: str,
        is_client_money: bool,
        actor: str,
    ) -> CashPosition:
        """Parse amount string and persist a new cash position."""
        amount = Decimal(amount_str)
        pos = CashPosition(
            id=str(uuid.uuid4()),
            pool_id=pool_id,
            amount=amount,
            currency=currency,
            value_date=datetime.now(UTC),
            description=description,
            is_client_money=is_client_money,
        )
        await self._store.add_position(pos)
        await self._audit.log(
            event_type="liquidity.position_added",
            entity_id=pool_id,
            details={
                "position_id": pos.id,
                "amount": str(amount),
                "currency": currency,
                "is_client_money": is_client_money,
            },
            actor=actor,
        )
        return pos

    async def get_pool_summary(self, pool_id: str) -> dict:
        """Return a summary dict for a pool including compliance status."""
        pool = await self._store.get_pool(pool_id)
        if pool is None:
            raise ValueError(f"Pool {pool_id!r} not found")
        positions = await self._store.list_positions(pool_id)
        surplus_or_deficit = pool.current_balance - pool.required_minimum
        is_compliant = pool.current_balance >= pool.required_minimum
        return {
            "pool_id": pool.id,
            "name": pool.name,
            "currency": pool.currency,
            "current_balance": str(pool.current_balance),
            "required_minimum": str(pool.required_minimum),
            "surplus_or_deficit": str(surplus_or_deficit),
            "position_count": len(positions),
            "is_compliant": is_compliant,
            "status": pool.status.value,
        }

    async def check_compliance(self, pool_id: str) -> bool:
        """Return True if pool balance >= required_minimum."""
        pool = await self._store.get_pool(pool_id)
        if pool is None:
            raise ValueError(f"Pool {pool_id!r} not found")
        return pool.current_balance >= pool.required_minimum

    async def get_all_pools(self) -> list[LiquidityPool]:
        """Return all registered liquidity pools."""
        return await self._store.list_pools()
