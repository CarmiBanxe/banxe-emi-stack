"""ADR-078 D3 — LiquidityForecastPort (read-only contract). No model runs, no mutation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal


class LiquidityForecastPortError(Exception):
    """Raised on liquidity forecast read failures."""


class LiquidityForecastPort(ABC):
    @abstractmethod
    def get_forecast_inputs(self) -> dict[str, Decimal]:
        """Return read-only inputs feeding the rolling liquidity forecast."""

    @abstractmethod
    def get_current_position(self) -> Decimal:
        """Return current liquidity position (read-only)."""


class InMemoryLiquidityForecastPort(LiquidityForecastPort):
    def __init__(
        self, inputs: dict[str, Decimal] | None = None, position: Decimal = Decimal("0")
    ) -> None:
        self._inputs = dict(inputs or {})
        self._position = position

    def get_forecast_inputs(self) -> dict[str, Decimal]:
        return dict(self._inputs)

    def get_current_position(self) -> Decimal:
        return self._position
