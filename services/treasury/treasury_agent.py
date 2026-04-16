"""
services/treasury/treasury_agent.py
IL-TLM-01 | Phase 17

Treasury Agent — orchestrates liquidity monitoring, forecasting, sweeps.
L2: monitoring + forecasting (auto-execute, alerts)
L4: sweep execution (HITL — I-27: irreversible fund movement)
"""

from __future__ import annotations

from decimal import Decimal

from services.treasury.cash_flow_forecaster import CashFlowForecaster
from services.treasury.funding_optimizer import FundingOptimizer
from services.treasury.liquidity_monitor import LiquidityMonitor
from services.treasury.models import (
    ForecastHorizon,
    SafeguardingAccount,
    SweepDirection,
    TreasuryAuditPort,
)
from services.treasury.safeguarding_reconciler import SafeguardingReconciler
from services.treasury.sweep_engine import SweepEngine


def _forecast_result_to_dict(fr) -> dict:  # type: ignore[no-untyped-def]
    return {
        "id": fr.id,
        "pool_id": fr.pool_id,
        "horizon": fr.horizon.value,
        "forecast_amount": str(fr.forecast_amount),
        "confidence": str(fr.confidence),
        "generated_at": fr.generated_at.isoformat(),
        "model_version": fr.model_version,
        "shortfall_risk": fr.shortfall_risk,
    }


def _sweep_event_to_dict(s) -> dict:  # type: ignore[no-untyped-def]
    return {
        "id": s.id,
        "pool_id": s.pool_id,
        "direction": s.direction.value,
        "amount": str(s.amount),
        "currency": s.currency,
        "executed_at": s.executed_at.isoformat() if s.executed_at else None,
        "proposed_at": s.proposed_at.isoformat(),
        "approved_by": s.approved_by,
        "description": s.description,
    }


def _recon_record_to_dict(r) -> dict:  # type: ignore[no-untyped-def]
    return {
        "id": r.id,
        "account_id": r.account_id,
        "period_date": r.period_date.isoformat(),
        "book_balance": str(r.book_balance),
        "bank_balance": str(r.bank_balance),
        "variance": str(r.variance),
        "status": r.status.value,
        "reconciled_at": r.reconciled_at.isoformat() if r.reconciled_at else None,
        "notes": r.notes,
    }


def _rec_to_dict(r) -> dict:  # type: ignore[no-untyped-def]
    return {
        "pool_id": r.pool_id,
        "action": r.action,
        "amount": str(r.amount),
        "funding_source_id": r.funding_source_id,
        "rationale": r.rationale,
    }


class TreasuryAgent:
    """Orchestrator for all treasury operations (liquidity, forecasting, sweeps)."""

    def __init__(
        self,
        monitor: LiquidityMonitor,
        forecaster: CashFlowForecaster,
        optimizer: FundingOptimizer,
        reconciler: SafeguardingReconciler,
        sweep_engine: SweepEngine,
        audit: TreasuryAuditPort,
    ) -> None:
        self._monitor = monitor
        self._forecaster = forecaster
        self._optimizer = optimizer
        self._reconciler = reconciler
        self._sweep_engine = sweep_engine
        self._audit = audit

    async def get_positions(self, pool_id: str, actor: str) -> dict:
        """Return pool summary dict for a single pool."""
        return await self._monitor.get_pool_summary(pool_id)

    async def run_forecast(self, pool_id: str, horizon_str: str, actor: str) -> dict:
        """Parse horizon and run cash flow forecast, returning serialised dict."""
        try:
            horizon = ForecastHorizon(horizon_str)
        except ValueError:
            raise ValueError(
                f"Invalid horizon {horizon_str!r}. "
                f"Valid values: {[h.value for h in ForecastHorizon]}"
            )
        result = await self._forecaster.forecast(pool_id, horizon, actor)
        return _forecast_result_to_dict(result)

    async def get_all_positions(self, actor: str) -> list[dict]:
        """Return pool summaries for every registered pool."""
        pools = await self._monitor.get_all_pools()
        summaries = []
        for pool in pools:
            summaries.append(await self._monitor.get_pool_summary(pool.id))
        return summaries

    async def optimize_allocation(self, actor: str) -> list[dict]:
        """Generate allocation recommendations for all pools."""
        pools = await self._monitor.get_all_pools()
        pool_ids = [p.id for p in pools]
        recs = await self._optimizer.optimize(pool_ids, actor)
        return [_rec_to_dict(r) for r in recs]

    async def propose_sweep(
        self,
        pool_id: str,
        direction_str: str,
        amount_str: str,
        actor: str,
        description: str = "",
    ) -> dict:
        """Parse direction and propose a sweep (HITL gate applied)."""
        try:
            direction = SweepDirection(direction_str)
        except ValueError:
            raise ValueError(
                f"Invalid direction {direction_str!r}. "
                f"Valid values: {[d.value for d in SweepDirection]}"
            )
        event = await self._sweep_engine.propose_sweep(
            pool_id, direction, amount_str, actor, description
        )
        return _sweep_event_to_dict(event)

    async def approve_sweep(self, sweep_id: str, approved_by: str) -> dict:
        """Approve and execute a pending sweep."""
        event = await self._sweep_engine.approve_and_execute(sweep_id, approved_by)
        return _sweep_event_to_dict(event)

    async def reconcile_account(
        self,
        account: SafeguardingAccount,
        bank_balance_str: str,
        actor: str,
    ) -> dict:
        """Parse bank balance string and run safeguarding reconciliation."""
        bank_balance = Decimal(bank_balance_str)
        record = await self._reconciler.reconcile(account, bank_balance, actor)
        return _recon_record_to_dict(record)

    async def get_pending_sweeps(self, pool_id: str | None = None) -> list[dict]:
        """Return pending (unapproved) sweeps."""
        sweeps = await self._sweep_engine.list_pending_sweeps(pool_id)
        return [_sweep_event_to_dict(s) for s in sweeps]

    async def get_audit_log(self, entity_id: str | None = None) -> list[dict]:
        """Return treasury audit log, optionally filtered by entity_id."""
        return await self._audit.list_events(entity_id)
