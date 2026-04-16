"""
services/treasury/sweep_engine.py
IL-TLM-01 | Phase 17

Automated sweep rules: surplus → investment, deficit → funding source.
All sweep executions require HITL approval (I-27).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import uuid

from services.treasury.models import (
    LiquidityStorePort,
    SweepDirection,
    SweepEvent,
    SweepStorePort,
    TreasuryAuditPort,
)


class SweepEngine:
    """Proposes and executes (post-HITL) treasury sweep operations.

    All sweeps are PROPOSED first with approved_by=None.
    Execution only occurs after explicit HITL approval (I-27).
    """

    def __init__(
        self,
        store: LiquidityStorePort,
        sweep_store: SweepStorePort,
        audit: TreasuryAuditPort,
    ) -> None:
        self._store = store
        self._sweep_store = sweep_store
        self._audit = audit

    async def propose_sweep(
        self,
        pool_id: str,
        direction: SweepDirection,
        amount_str: str,
        actor: str,
        description: str = "",
    ) -> SweepEvent:
        """Propose a treasury sweep — awaits HITL approval before execution."""
        amount = Decimal(amount_str)
        if amount <= Decimal("0"):
            raise ValueError(f"Sweep amount must be positive, got {amount_str!r}")

        pool = await self._store.get_pool(pool_id)
        if pool is None:
            raise ValueError(f"Pool {pool_id!r} not found")

        event = SweepEvent(
            id=str(uuid.uuid4()),
            pool_id=pool_id,
            direction=direction,
            amount=amount,
            currency=pool.currency,
            executed_at=None,
            proposed_at=datetime.now(UTC),
            approved_by=None,
            description=description,
        )
        await self._sweep_store.save_sweep(event)
        await self._audit.log(
            event_type="sweep.proposed",
            entity_id=pool_id,
            details={
                "sweep_id": event.id,
                "direction": direction.value,
                "amount": str(amount),
                "currency": pool.currency,
            },
            actor=actor,
        )
        return event

    async def approve_and_execute(self, sweep_id: str, approved_by: str) -> SweepEvent:
        """Approve a pending sweep and mark it as executed.

        In production this would also update pool balance + call ASPSP.
        """
        updated = await self._sweep_store.approve_sweep(sweep_id, approved_by)
        await self._audit.log(
            event_type="sweep.approved_and_executed",
            entity_id=updated.pool_id,
            details={
                "sweep_id": sweep_id,
                "approved_by": approved_by,
                "executed_at": updated.executed_at.isoformat() if updated.executed_at else None,
            },
            actor=approved_by,
        )
        return updated

    async def list_pending_sweeps(self, pool_id: str | None = None) -> list[SweepEvent]:
        """Return sweeps awaiting HITL approval."""
        all_sweeps = await self._sweep_store.list_sweeps(pool_id)
        return [s for s in all_sweeps if s.approved_by is None]

    async def list_all_sweeps(self, pool_id: str | None = None) -> list[SweepEvent]:
        """Return all sweeps including approved and pending."""
        return await self._sweep_store.list_sweeps(pool_id)
