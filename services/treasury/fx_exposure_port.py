"""ADR-078 D1 — FXExposurePort (read-only contract). No trade execution."""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal


class FXExposurePortError(Exception):
    """Raised on FX exposure read failures."""


class FXExposurePort(ABC):
    @abstractmethod
    def get_exposure(self, ccy: str) -> Decimal:
        """Return signed FX exposure for a single currency (read-only)."""

    @abstractmethod
    def get_total_exposure(self) -> Decimal:
        """Return aggregate absolute FX exposure across all currencies."""


class InMemoryFXExposurePort(FXExposurePort):
    def __init__(self, positions: dict[str, Decimal] | None = None) -> None:
        self._positions: dict[str, Decimal] = dict(positions or {})

    def get_exposure(self, ccy: str) -> Decimal:
        if ccy not in self._positions:
            raise FXExposurePortError(f"unknown ccy: {ccy}")
        return self._positions[ccy]

    def get_total_exposure(self) -> Decimal:
        return sum((abs(v) for v in self._positions.values()), Decimal("0"))
