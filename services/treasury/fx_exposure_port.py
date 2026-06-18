"""ADR-078 D1 — FXExposurePort (read-only). Frozen value objects, async, no trades."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal


class FXExposurePortError(Exception):
    """Raised on FX exposure read failures."""


@dataclass(frozen=True)
class FXPosition:
    currency_pair: str
    net_exposure_gbp: Decimal
    as_of: str


@dataclass(frozen=True)
class FXExposureView:
    as_of: str
    positions: tuple[FXPosition, ...]
    total_net_exposure_gbp: Decimal


class FXExposurePort(ABC):
    @abstractmethod
    async def get_exposure(self, currency_pair: str) -> FXPosition: ...
    @abstractmethod
    async def get_total_exposure(self) -> FXExposureView: ...


class InMemoryFXExposurePort(FXExposurePort):
    def __init__(self) -> None:
        self._positions: dict[str, FXPosition] = {}

    def seed(self, position: FXPosition) -> None:
        self._positions[position.currency_pair] = position

    async def get_exposure(self, currency_pair: str) -> FXPosition:
        if currency_pair not in self._positions:
            raise FXExposurePortError(f"unknown currency_pair: {currency_pair}")
        return self._positions[currency_pair]

    async def get_total_exposure(self) -> FXExposureView:
        positions = tuple(self._positions.values())
        as_of = positions[0].as_of if positions else ""
        total = sum((abs(p.net_exposure_gbp) for p in positions), Decimal("0"))
        return FXExposureView(as_of=as_of, positions=positions, total_net_exposure_gbp=total)
