"""
api/routers/treasury.py
IL-TLM-01 | Phase 17

Treasury & Liquidity Management REST API.
Endpoints:
  GET  /v1/treasury/positions                → all pool summaries
  GET  /v1/treasury/positions/{pool_id}      → single pool summary
  GET  /v1/treasury/forecasts/{pool_id}      → cash flow forecast
  GET  /v1/treasury/sweeps/pending           → pending sweeps list
  POST /v1/treasury/sweeps                   → propose sweep
  POST /v1/treasury/sweeps/{sweep_id}/approve → approve sweep
  GET  /v1/treasury/reconciliations          → reconciliation list
  POST /v1/treasury/reconcile               → trigger reconciliation

FCA compliance:
  - All amounts returned as strings (I-05, never float)
  - HITL required for sweep execution (I-27)
  - CASS 15.3 safeguarding reconciliation supported
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from services.treasury.cash_flow_forecaster import CashFlowForecaster
from services.treasury.funding_optimizer import FundingOptimizer
from services.treasury.liquidity_monitor import LiquidityMonitor
from services.treasury.models import (
    InMemoryForecastStore,
    InMemoryLiquidityStore,
    InMemoryReconciliationStore,
    InMemorySweepStore,
    InMemoryTreasuryAudit,
    SafeguardingAccount,
    make_sample_pool,
)
from services.treasury.safeguarding_reconciler import SafeguardingReconciler
from services.treasury.sweep_engine import SweepEngine
from services.treasury.treasury_agent import TreasuryAgent

router = APIRouter(tags=["treasury"])

# ── Pydantic request models ────────────────────────────────────────────────────


class ProposeSweepRequest(BaseModel):
    pool_id: str
    direction: str
    amount: str
    actor: str
    description: str = ""


class ApproveSweepRequest(BaseModel):
    approved_by: str


class ReconcileRequest(BaseModel):
    institution: str
    iban: str
    balance: str
    client_money: str
    currency: str = "GBP"


# ── Agent factory (seeded once) ────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _get_agent() -> TreasuryAgent:
    """Build TreasuryAgent wired to InMemory stubs with a seeded sample pool."""
    liquidity_store = InMemoryLiquidityStore()
    forecast_store = InMemoryForecastStore()
    sweep_store = InMemorySweepStore()
    recon_store = InMemoryReconciliationStore()
    audit = InMemoryTreasuryAudit()

    # Seed one sample pool so GET endpoints return data immediately
    import asyncio

    sample_pool = make_sample_pool("pool-001")
    asyncio.get_event_loop().run_until_complete(liquidity_store.save_pool(sample_pool))

    monitor = LiquidityMonitor(liquidity_store, audit)
    forecaster = CashFlowForecaster(liquidity_store, forecast_store, audit)
    optimizer = FundingOptimizer(liquidity_store, audit)
    reconciler = SafeguardingReconciler(recon_store, audit)
    sweep_engine = SweepEngine(liquidity_store, sweep_store, audit)

    return TreasuryAgent(monitor, forecaster, optimizer, reconciler, sweep_engine, audit)


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.get("/treasury/positions")
async def get_all_positions() -> list[dict[str, Any]]:
    """Return summaries for all registered liquidity pools."""
    agent = _get_agent()
    return await agent.get_all_positions(actor="api")


@router.get("/treasury/positions/{pool_id}")
async def get_pool_positions(pool_id: str) -> dict[str, Any]:
    """Return summary for a specific pool."""
    agent = _get_agent()
    try:
        return await agent.get_positions(pool_id, actor="api")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/treasury/forecasts/{pool_id}")
async def run_forecast(
    pool_id: str,
    horizon: str = Query(default="DAYS_7", description="DAYS_7 | DAYS_14 | DAYS_30"),
) -> dict[str, Any]:
    """Run a cash flow forecast for a pool."""
    agent = _get_agent()
    try:
        return await agent.run_forecast(pool_id, horizon, actor="api")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/treasury/sweeps/pending")
async def list_pending_sweeps(
    pool_id: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    """List sweeps awaiting HITL approval."""
    agent = _get_agent()
    return await agent.get_pending_sweeps(pool_id)


@router.post("/treasury/sweeps")
async def propose_sweep(req: ProposeSweepRequest) -> dict[str, Any]:
    """Propose a treasury sweep (HITL approval required before execution)."""
    agent = _get_agent()
    try:
        return await agent.propose_sweep(
            pool_id=req.pool_id,
            direction_str=req.direction,
            amount_str=req.amount,
            actor=req.actor,
            description=req.description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/treasury/sweeps/{sweep_id}/approve")
async def approve_sweep(sweep_id: str, req: ApproveSweepRequest) -> dict[str, Any]:
    """Approve and execute a pending sweep (HITL gate)."""
    agent = _get_agent()
    try:
        return await agent.approve_sweep(sweep_id, req.approved_by)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/treasury/reconciliations")
async def list_reconciliations(
    account_id: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    """List safeguarding reconciliation records."""
    agent = _get_agent()
    records = await agent._reconciler.list_reconciliations(account_id)
    return [
        {
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
        for r in records
    ]


@router.post("/treasury/reconcile")
async def manual_reconcile(req: ReconcileRequest) -> dict[str, Any]:
    """Trigger a manual safeguarding reconciliation for an account."""
    agent = _get_agent()
    account = SafeguardingAccount(
        id=f"acc-{req.iban[-8:]}",
        institution=req.institution,
        iban=req.iban,
        balance=Decimal(req.balance),
        client_money_held=Decimal(req.client_money),
        currency=req.currency,
        last_reconciled_at=datetime.now(UTC),
    )
    try:
        return await agent.reconcile_account(account, req.balance, actor="api")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
