"""
tests/test_treasury/test_agent.py
IL-TLM-01 | Phase 17 — TreasuryAgent orchestration tests.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

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

_NOW = datetime.now(UTC)


def _make_agent() -> TreasuryAgent:
    store = InMemoryLiquidityStore()
    fstore = InMemoryForecastStore()
    sweep_store = InMemorySweepStore()
    recon_store = InMemoryReconciliationStore()
    audit = InMemoryTreasuryAudit()
    monitor = LiquidityMonitor(store, audit)
    forecaster = CashFlowForecaster(store, fstore, audit)
    optimizer = FundingOptimizer(store, audit)
    reconciler = SafeguardingReconciler(recon_store, audit)
    sweep_engine = SweepEngine(store, sweep_store, audit)
    return TreasuryAgent(monitor, forecaster, optimizer, reconciler, sweep_engine, audit)


async def _seeded_agent() -> TreasuryAgent:
    agent = _make_agent()
    await agent._monitor._store.save_pool(make_sample_pool())
    return agent


def _sample_account() -> SafeguardingAccount:
    return SafeguardingAccount(
        id="acc-001",
        institution="Barclays",
        iban="GB29NWBK60161331926819",
        balance=Decimal("100000"),
        client_money_held=Decimal("95000"),
        currency="GBP",
        last_reconciled_at=_NOW,
    )


@pytest.mark.asyncio
async def test_get_positions_returns_dict_with_pool_id() -> None:
    agent = await _seeded_agent()
    result = await agent.get_positions("pool-001", "actor")
    assert "pool_id" in result


@pytest.mark.asyncio
async def test_get_all_positions_returns_list_with_at_least_one() -> None:
    agent = await _seeded_agent()
    results = await agent.get_all_positions("actor")
    assert isinstance(results, list)
    assert len(results) >= 1


@pytest.mark.asyncio
async def test_run_forecast_returns_dict_with_forecast_amount() -> None:
    agent = await _seeded_agent()
    result = await agent.run_forecast("pool-001", "DAYS_7", "actor")
    assert "forecast_amount" in result


@pytest.mark.asyncio
async def test_run_forecast_invalid_horizon_raises_value_error() -> None:
    agent = await _seeded_agent()
    with pytest.raises(ValueError):
        await agent.run_forecast("pool-001", "DAYS_99", "actor")


@pytest.mark.asyncio
async def test_optimize_allocation_returns_list_of_recommendations() -> None:
    agent = await _seeded_agent()
    results = await agent.optimize_allocation("actor")
    assert isinstance(results, list)
    assert len(results) >= 1


@pytest.mark.asyncio
async def test_propose_sweep_returns_dict_with_id() -> None:
    agent = await _seeded_agent()
    result = await agent.propose_sweep("pool-001", "SURPLUS_OUT", "50000", "actor")
    assert "id" in result


@pytest.mark.asyncio
async def test_propose_sweep_approved_by_is_none() -> None:
    agent = await _seeded_agent()
    result = await agent.propose_sweep("pool-001", "SURPLUS_OUT", "50000", "actor")
    assert result["approved_by"] is None


@pytest.mark.asyncio
async def test_approve_sweep_returns_dict_with_approved_by_set() -> None:
    agent = await _seeded_agent()
    proposed = await agent.propose_sweep("pool-001", "SURPLUS_OUT", "50000", "actor")
    approved = await agent.approve_sweep(proposed["id"], "mlro")
    assert approved["approved_by"] == "mlro"


@pytest.mark.asyncio
async def test_reconcile_account_returns_dict_with_status() -> None:
    agent = await _seeded_agent()
    result = await agent.reconcile_account(_sample_account(), "100000", "actor")
    assert "status" in result


@pytest.mark.asyncio
async def test_reconcile_account_matched_when_balances_equal() -> None:
    agent = await _seeded_agent()
    result = await agent.reconcile_account(_sample_account(), "100000", "actor")
    assert result["status"] == "MATCHED"


@pytest.mark.asyncio
async def test_reconcile_account_discrepancy_when_variance_above_threshold() -> None:
    agent = await _seeded_agent()
    result = await agent.reconcile_account(_sample_account(), "99000", "actor")
    assert result["status"] == "DISCREPANCY"


@pytest.mark.asyncio
async def test_get_pending_sweeps_returns_list() -> None:
    agent = await _seeded_agent()
    result = await agent.get_pending_sweeps()
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_get_audit_log_returns_list_of_dicts() -> None:
    agent = await _seeded_agent()
    await agent.get_positions("pool-001", "actor")
    log = await agent.get_audit_log()
    assert isinstance(log, list)


@pytest.mark.asyncio
async def test_get_audit_log_contains_events_after_operations() -> None:
    agent = await _seeded_agent()
    await agent.run_forecast("pool-001", "DAYS_7", "actor")
    log = await agent.get_audit_log()
    event_types = [e["event_type"] for e in log]
    assert "forecast.generated" in event_types


@pytest.mark.asyncio
async def test_run_forecast_days_7() -> None:
    agent = await _seeded_agent()
    result = await agent.run_forecast("pool-001", "DAYS_7", "actor")
    assert result["horizon"] == "DAYS_7"


@pytest.mark.asyncio
async def test_run_forecast_days_14() -> None:
    agent = await _seeded_agent()
    result = await agent.run_forecast("pool-001", "DAYS_14", "actor")
    assert result["horizon"] == "DAYS_14"


@pytest.mark.asyncio
async def test_run_forecast_days_30() -> None:
    agent = await _seeded_agent()
    result = await agent.run_forecast("pool-001", "DAYS_30", "actor")
    assert result["horizon"] == "DAYS_30"


@pytest.mark.asyncio
async def test_get_positions_pool_not_found_raises_value_error() -> None:
    agent = _make_agent()
    with pytest.raises(ValueError):
        await agent.get_positions("nonexistent-pool", "actor")


@pytest.mark.asyncio
async def test_propose_sweep_invalid_direction_raises_value_error() -> None:
    agent = await _seeded_agent()
    with pytest.raises(ValueError):
        await agent.propose_sweep("pool-001", "INVALID_DIR", "1000", "actor")


@pytest.mark.asyncio
async def test_reconcile_account_variance_is_string() -> None:
    agent = await _seeded_agent()
    result = await agent.reconcile_account(_sample_account(), "99000", "actor")
    assert isinstance(result["variance"], str)
