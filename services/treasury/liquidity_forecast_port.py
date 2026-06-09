from __future__ import annotations

import abc
from dataclasses import dataclass
from decimal import Decimal


class LiquidityForecastPortError(Exception):
    """Raised when LiquidityForecastPort cannot fulfil a request."""


@dataclass(frozen=True)
class LiquidityForecastInputs:
    as_of: str
    horizon_days: int
    opening_balance_gbp: Decimal
    projected_inflows_gbp: Decimal
    projected_outflows_gbp: Decimal


class LiquidityForecastPort(abc.ABC):
    """Supply read-only inputs for a rolling liquidity forecast.

    DOES: provide opening balance, projected inflows/outflows, current position.
    DOES NOT: execute forecasting models or distribute forecast packs.
    soul: forecast-agent — modelling and distribution are out of scope.
    """

    @abc.abstractmethod
    async def get_forecast_inputs(self, horizon_days: int) -> LiquidityForecastInputs:
        """Return forecast inputs for the requested horizon."""
        ...  # pragma: no cover

    @abc.abstractmethod
    async def get_current_position(self, as_of: str) -> Decimal:
        """Return current GBP liquidity position as of a date."""
        ...  # pragma: no cover


class InMemoryLiquidityForecastPort(LiquidityForecastPort):
    """Configurable in-memory stub for unit tests."""

    def __init__(
        self,
        inputs: LiquidityForecastInputs | None = None,
        current_position: Decimal = Decimal("0"),
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

    async def get_current_position(self, as_of: str) -> Decimal:
        if self._position_raises is not None:
            raise self._position_raises
        return self._current_position
