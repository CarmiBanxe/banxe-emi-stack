from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from services.treasury.liquidity_forecast_port import (
    InMemoryLiquidityForecastPort,
    LiquidityForecastInputs,
    LiquidityForecastPortError,
)


def _inputs(horizon_days: int = 30) -> LiquidityForecastInputs:
    return LiquidityForecastInputs(
        as_of="2026-06-09",
        horizon_days=horizon_days,
        opening_balance_gbp=Decimal("500000.00"),
        projected_inflows_gbp=Decimal("200000.00"),
        projected_outflows_gbp=Decimal("150000.00"),
    )


async def test_get_forecast_inputs_returns_configured() -> None:
    port = InMemoryLiquidityForecastPort(inputs=_inputs(30))
    result = await port.get_forecast_inputs(30)
    assert result.horizon_days == 30
    assert result.opening_balance_gbp == Decimal("500000.00")


async def test_get_forecast_inputs_no_inputs_raises() -> None:
    port = InMemoryLiquidityForecastPort()
    with pytest.raises(LiquidityForecastPortError, match="No forecast inputs"):
        await port.get_forecast_inputs(30)


async def test_get_forecast_inputs_custom_raises_propagated() -> None:
    err = LiquidityForecastPortError("upstream error")
    port = InMemoryLiquidityForecastPort(inputs_raises=err)
    with pytest.raises(LiquidityForecastPortError, match="upstream error"):
        await port.get_forecast_inputs(30)


async def test_get_current_position_returns_configured() -> None:
    port = InMemoryLiquidityForecastPort(current_position=Decimal("750000.00"))
    result = await port.get_current_position("2026-06-09")
    assert result == Decimal("750000.00")


async def test_get_current_position_default_zero() -> None:
    port = InMemoryLiquidityForecastPort()
    result = await port.get_current_position("2026-06-09")
    assert result == Decimal("0")


async def test_get_current_position_raises_propagated() -> None:
    err = LiquidityForecastPortError("position unavailable")
    port = InMemoryLiquidityForecastPort(position_raises=err)
    with pytest.raises(LiquidityForecastPortError, match="position unavailable"):
        await port.get_current_position("2026-06-09")


async def test_inputs_frozen_value_object() -> None:
    inp = _inputs(60)
    with pytest.raises(FrozenInstanceError):
        inp.horizon_days = 90  # type: ignore[misc]
