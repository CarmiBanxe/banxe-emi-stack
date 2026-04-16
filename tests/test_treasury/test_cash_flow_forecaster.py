"""
tests/test_treasury/test_cash_flow_forecaster.py
IL-TLM-01 | Phase 17 — CashFlowForecaster tests.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from services.treasury.cash_flow_forecaster import CashFlowForecaster
from services.treasury.models import (
    CashPosition,
    ForecastHorizon,
    InMemoryForecastStore,
    InMemoryLiquidityStore,
    InMemoryTreasuryAudit,
    LiquidityPool,
    PoolStatus,
    make_sample_pool,
)

_NOW = datetime.now(UTC)


def _make_forecaster(
    pool: LiquidityPool | None = None,
) -> tuple[
    CashFlowForecaster, InMemoryLiquidityStore, InMemoryForecastStore, InMemoryTreasuryAudit
]:
    store = InMemoryLiquidityStore()
    fstore = InMemoryForecastStore()
    audit = InMemoryTreasuryAudit()
    forecaster = CashFlowForecaster(store, fstore, audit)
    return forecaster, store, fstore, audit


async def _add_positions(store: InMemoryLiquidityStore, pool_id: str, amounts: list[str]) -> None:
    for i, amt in enumerate(amounts):
        pos = CashPosition(
            id=f"pos-{i}",
            pool_id=pool_id,
            amount=Decimal(amt),
            currency="GBP",
            value_date=_NOW,
            description=f"pos {i}",
            is_client_money=False,
        )
        await store.add_position(pos)


@pytest.mark.asyncio
async def test_forecast_pool_no_positions_returns_result() -> None:
    forecaster, store, _, _ = _make_forecaster()
    await store.save_pool(make_sample_pool())
    result = await forecaster.forecast("pool-001", ForecastHorizon.DAYS_7, "actor")
    assert result is not None


@pytest.mark.asyncio
async def test_forecast_result_amount_is_decimal() -> None:
    forecaster, store, _, _ = _make_forecaster()
    await store.save_pool(make_sample_pool())
    result = await forecaster.forecast("pool-001", ForecastHorizon.DAYS_7, "actor")
    assert isinstance(result.forecast_amount, Decimal)


@pytest.mark.asyncio
async def test_forecast_result_confidence_is_decimal() -> None:
    forecaster, store, _, _ = _make_forecaster()
    await store.save_pool(make_sample_pool())
    result = await forecaster.forecast("pool-001", ForecastHorizon.DAYS_7, "actor")
    assert isinstance(result.confidence, Decimal)


@pytest.mark.asyncio
async def test_forecast_shortfall_risk_true_when_below_minimum() -> None:
    pool = LiquidityPool(
        id="pool-low",
        name="Low",
        currency="GBP",
        current_balance=Decimal("100000"),
        required_minimum=Decimal("500000"),
        status=PoolStatus.ACTIVE,
        aspsp_account_id="a",
        updated_at=_NOW,
    )
    forecaster, store, _, _ = _make_forecaster()
    await store.save_pool(pool)
    result = await forecaster.forecast("pool-low", ForecastHorizon.DAYS_7, "actor")
    assert result.shortfall_risk is True


@pytest.mark.asyncio
async def test_forecast_shortfall_risk_false_when_above_minimum() -> None:
    forecaster, store, _, _ = _make_forecaster()
    await store.save_pool(make_sample_pool())
    result = await forecaster.forecast("pool-001", ForecastHorizon.DAYS_7, "actor")
    assert result.shortfall_risk is False


@pytest.mark.asyncio
async def test_forecast_with_3_positions_uses_average() -> None:
    forecaster, store, _, _ = _make_forecaster()
    await store.save_pool(make_sample_pool())
    await _add_positions(store, "pool-001", ["100", "200", "300"])
    result = await forecaster.forecast("pool-001", ForecastHorizon.DAYS_7, "actor")
    # average of [100, 200, 300] = 200
    assert result.forecast_amount == Decimal("200")


@pytest.mark.asyncio
async def test_forecast_different_horizons_yield_separate_objects() -> None:
    forecaster, store, _, _ = _make_forecaster()
    await store.save_pool(make_sample_pool())
    r7 = await forecaster.forecast("pool-001", ForecastHorizon.DAYS_7, "actor")
    r14 = await forecaster.forecast("pool-001", ForecastHorizon.DAYS_14, "actor")
    assert r7.id != r14.id
    assert r7.horizon != r14.horizon


@pytest.mark.asyncio
async def test_forecast_saves_to_forecast_store() -> None:
    forecaster, store, fstore, _ = _make_forecaster()
    await store.save_pool(make_sample_pool())
    result = await forecaster.forecast("pool-001", ForecastHorizon.DAYS_7, "actor")
    latest = await fstore.get_latest("pool-001", ForecastHorizon.DAYS_7)
    assert latest is not None
    assert latest.id == result.id


@pytest.mark.asyncio
async def test_forecast_creates_audit_entry() -> None:
    forecaster, store, _, audit = _make_forecaster()
    await store.save_pool(make_sample_pool())
    await forecaster.forecast("pool-001", ForecastHorizon.DAYS_7, "actor")
    events = await audit.list_events("pool-001")
    event_types = [e["event_type"] for e in events]
    assert "forecast.generated" in event_types


@pytest.mark.asyncio
async def test_get_latest_forecast_returns_saved() -> None:
    forecaster, store, _, _ = _make_forecaster()
    await store.save_pool(make_sample_pool())
    await forecaster.forecast("pool-001", ForecastHorizon.DAYS_7, "actor")
    latest = await forecaster.get_latest_forecast("pool-001", ForecastHorizon.DAYS_7)
    assert latest is not None


@pytest.mark.asyncio
async def test_get_latest_forecast_none_if_not_computed() -> None:
    forecaster, store, _, _ = _make_forecaster()
    await store.save_pool(make_sample_pool())
    latest = await forecaster.get_latest_forecast("pool-001", ForecastHorizon.DAYS_7)
    assert latest is None


@pytest.mark.asyncio
async def test_list_forecasts_returns_all_for_pool() -> None:
    forecaster, store, _, _ = _make_forecaster()
    await store.save_pool(make_sample_pool())
    await forecaster.forecast("pool-001", ForecastHorizon.DAYS_7, "actor")
    await forecaster.forecast("pool-001", ForecastHorizon.DAYS_14, "actor")
    results = await forecaster.list_forecasts("pool-001")
    assert len(results) == 2


@pytest.mark.asyncio
async def test_list_forecasts_empty_for_unknown_pool() -> None:
    forecaster, _, _, _ = _make_forecaster()
    results = await forecaster.list_forecasts("unknown-pool")
    assert results == []


@pytest.mark.asyncio
async def test_forecast_model_version_in_result() -> None:
    forecaster, store, _, _ = _make_forecaster()
    await store.save_pool(make_sample_pool())
    result = await forecaster.forecast("pool-001", ForecastHorizon.DAYS_7, "actor")
    assert result.model_version != ""


@pytest.mark.asyncio
async def test_forecast_with_days_30_horizon() -> None:
    forecaster, store, _, _ = _make_forecaster()
    await store.save_pool(make_sample_pool())
    result = await forecaster.forecast("pool-001", ForecastHorizon.DAYS_30, "actor")
    assert result.horizon == ForecastHorizon.DAYS_30


@pytest.mark.asyncio
async def test_forecast_nonexistent_pool_raises_value_error() -> None:
    forecaster, _, _, _ = _make_forecaster()
    with pytest.raises(ValueError):
        await forecaster.forecast("ghost-pool", ForecastHorizon.DAYS_7, "actor")


@pytest.mark.asyncio
async def test_forecast_confidence_between_0_and_1() -> None:
    forecaster, store, _, _ = _make_forecaster()
    await store.save_pool(make_sample_pool())
    result = await forecaster.forecast("pool-001", ForecastHorizon.DAYS_7, "actor")
    assert Decimal("0") <= result.confidence <= Decimal("1")


def test_compute_trend_with_2_positions_returns_average() -> None:
    forecaster, _, _, _ = _make_forecaster()
    pos1 = CashPosition(
        id="p1",
        pool_id="pool-001",
        amount=Decimal("100"),
        currency="GBP",
        value_date=_NOW,
        description="p1",
        is_client_money=False,
    )
    pos2 = CashPosition(
        id="p2",
        pool_id="pool-001",
        amount=Decimal("200"),
        currency="GBP",
        value_date=_NOW,
        description="p2",
        is_client_money=False,
    )
    result = forecaster._compute_trend([pos1, pos2])
    assert result == Decimal("150")
    assert isinstance(result, Decimal)


@pytest.mark.asyncio
async def test_two_forecasts_same_pool_horizon_get_latest_returns_most_recent() -> None:
    forecaster, store, fstore, _ = _make_forecaster()
    await store.save_pool(make_sample_pool())
    await forecaster.forecast("pool-001", ForecastHorizon.DAYS_7, "actor")
    r2 = await forecaster.forecast("pool-001", ForecastHorizon.DAYS_7, "actor")
    latest = await fstore.get_latest("pool-001", ForecastHorizon.DAYS_7)
    assert latest is not None
    assert latest.id == r2.id


@pytest.mark.asyncio
async def test_forecast_result_id_is_unique() -> None:
    forecaster, store, _, _ = _make_forecaster()
    await store.save_pool(make_sample_pool())
    r1 = await forecaster.forecast("pool-001", ForecastHorizon.DAYS_7, "actor")
    r2 = await forecaster.forecast("pool-001", ForecastHorizon.DAYS_14, "actor")
    assert r1.id != r2.id
