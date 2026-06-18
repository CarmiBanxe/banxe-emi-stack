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
    def __init__(
        self,
        inputs: LiquidityForecastInputs | None = None,
        current_position: Decimal | None = None,
        inputs_raises: Exception | None = None,
        position_raises: Exception | None = None,
    ) -> None:
        self._inputs = inputs
        self._current_position = current_position
        self._inputs_raises = inputs_raises
        self._position_raises = position_raises

    async def get_forecast_inputs(self, horizon_days: int) -> LiquidityForecastInputs:
        if self._inputs_raises is not None:
            raise self._inputs_raises
        if self._inputs is None:
            raise LiquidityForecastPortError("No forecast inputs configured")
        return self._inputs

    async def get_current_position(self, date: str) -> Decimal:
        if self._position_raises is not None:
            raise self._position_raises
        if self._current_position is None:
            return Decimal("0")
        return self._current_position
