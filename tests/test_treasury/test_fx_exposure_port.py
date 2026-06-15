from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from services.treasury.fx_exposure_port import (
    FXExposurePortError,
    FXPosition,
    InMemoryFXExposurePort,
)


def _pos(pair: str, amount: str = "1000.00", as_of: str = "2026-06-09") -> FXPosition:
    return FXPosition(currency_pair=pair, net_exposure_gbp=Decimal(amount), as_of=as_of)


async def test_get_exposure_known_pair_returns_position() -> None:
    port = InMemoryFXExposurePort([_pos("GBP/USD", "5000.00")])
    result = await port.get_exposure("GBP/USD")
    assert result.currency_pair == "GBP/USD"
    assert result.net_exposure_gbp == Decimal("5000.00")


async def test_get_exposure_unknown_pair_raises() -> None:
    port = InMemoryFXExposurePort([_pos("GBP/EUR")])
    with pytest.raises(FXExposurePortError, match="GBP/USD"):
        await port.get_exposure("GBP/USD")


async def test_get_total_exposure_sums_all_positions() -> None:
    port = InMemoryFXExposurePort(
        [
            _pos("GBP/USD", "3000.00"),
            _pos("GBP/EUR", "2000.00"),
        ]
    )
    view = await port.get_total_exposure()
    assert view.total_exposure_gbp == Decimal("5000.00")
    assert len(view.positions) == 2


async def test_get_total_exposure_empty_returns_zero() -> None:
    port = InMemoryFXExposurePort()
    view = await port.get_total_exposure()
    assert view.total_exposure_gbp == Decimal("0")
    assert view.positions == []
    assert view.as_of == "1970-01-01"


async def test_get_total_exposure_single_position_inherits_as_of() -> None:
    port = InMemoryFXExposurePort([_pos("GBP/JPY", "100.00", as_of="2026-05-01")])
    view = await port.get_total_exposure()
    assert view.as_of == "2026-05-01"


async def test_positions_are_frozen_value_objects() -> None:
    p = _pos("GBP/CHF", "999.99")
    with pytest.raises(FrozenInstanceError):
        p.net_exposure_gbp = Decimal("1")  # type: ignore[misc]
