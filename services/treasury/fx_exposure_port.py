from __future__ import annotations

import abc
from dataclasses import dataclass
from decimal import Decimal


class FXExposurePortError(Exception):
    """Raised when FXExposurePort cannot fulfil a request."""


@dataclass(frozen=True)
class FXPosition:
    currency_pair: str
    net_exposure_gbp: Decimal
    as_of: str


@dataclass(frozen=True)
class FXExposureView:
    positions: list[FXPosition]
    total_exposure_gbp: Decimal
    as_of: str


class FXExposurePort(abc.ABC):
    """Read net FX exposure per currency pair and aggregate total.

    DOES: read net FX positions; aggregate total exposure.
    DOES NOT: execute FX trades or hedges.
    soul: fx-exposure-agent — NEVER execute hedge trades.
    """

    @abc.abstractmethod
    async def get_exposure(self, currency_pair: str) -> FXPosition:
        """Return net GBP exposure for the given currency pair."""
        ...  # pragma: no cover

    @abc.abstractmethod
    async def get_total_exposure(self) -> FXExposureView:
        """Return aggregated FX exposure across all open positions."""
        ...  # pragma: no cover


class InMemoryFXExposurePort(FXExposurePort):
    """Configurable in-memory stub for unit tests."""

    def __init__(self, positions: list[FXPosition] | None = None) -> None:
        self._positions: dict[str, FXPosition] = {}
        for p in positions or []:
            self._positions[p.currency_pair] = p

    async def get_exposure(self, currency_pair: str) -> FXPosition:
        if currency_pair not in self._positions:
            raise FXExposurePortError(f"Unknown currency pair: {currency_pair!r}")
        return self._positions[currency_pair]

    async def get_total_exposure(self) -> FXExposureView:
        positions = list(self._positions.values())
        total = sum((p.net_exposure_gbp for p in positions), Decimal("0"))
        as_of = positions[0].as_of if positions else "1970-01-01"
        return FXExposureView(
            positions=positions,
            total_exposure_gbp=total,
            as_of=as_of,
        )
