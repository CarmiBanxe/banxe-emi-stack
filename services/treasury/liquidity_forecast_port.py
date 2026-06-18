"""ADR-078 D3 — LiquidityForecastPort (read-only). Frozen inputs, async, no model runs."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal


class LiquidityForecastPortError(Exception):
    """Raised on liquidity forecast read failures."""


@dataclass(frozen=True)
class LiquidityForecastInputs:
    as_of: str
    horizon_days: int
    opening_balance_gbp: Decimal
    projected_inflows_gbp: Decimal
    projected_outflows_gbp: Decimal


class LiquidityForecastPort(ABC):
    @abstractmethod
    async def get_forecast_inputs(self, horizon_days: int) -> LiquidityForecastInputs: ...
    @abstractmethod
    async def get_current_position(self, date: str) -> Decimal: ...


class InMemoryLiquidityForecastPort(LiquidityForecastPort):
    def __init__(self) -> None:
        self._inputs: dict[int, LiquidityForecastInputs] = {}
        self._positions: dict[str, Decimal] = {}

    def seed(self, inputs: LiquidityForecastInputs) -> None:
        self._inputs[inputs.horizon_days] = inputs

    def seed_position(self, date: str, amount: Decimal) -> None:
        self._positions[date] = amount

    async def get_forecast_inputs(self, horizon_days: int) -> LiquidityForecastInputs:
        if horizon_days not in self._inputs:
            raise LiquidityForecastPortError(f"no inputs for horizon {horizon_days}")
        return self._inputs[horizon_days]

    async def get_current_position(self, date: str) -> Decimal:
        if date not in self._positions:
            raise LiquidityForecastPortError(f"no position for {date}")
        return self._positions[date]
