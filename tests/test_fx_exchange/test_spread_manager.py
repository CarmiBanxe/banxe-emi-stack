"""tests/test_fx_exchange/test_spread_manager.py — SpreadManager tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.fx_exchange.models import CurrencyPair, SpreadConfig
from services.fx_exchange.spread_manager import SpreadManager


def _make_manager() -> SpreadManager:
    return SpreadManager()


@pytest.mark.asyncio
async def test_get_spread_known_pair():
    mgr = _make_manager()
    config = await mgr.get_spread(CurrencyPair("GBP", "EUR"))
    assert config.base_spread_bps == 20


@pytest.mark.asyncio
async def test_get_spread_gbp_usd():
    mgr = _make_manager()
    config = await mgr.get_spread(CurrencyPair("GBP", "USD"))
    assert config.base_spread_bps == 20


@pytest.mark.asyncio
async def test_get_spread_exotic_gbp_pln():
    mgr = _make_manager()
    config = await mgr.get_spread(CurrencyPair("GBP", "PLN"))
    assert config.base_spread_bps == 50


@pytest.mark.asyncio
async def test_get_spread_unknown_pair_returns_default():
    mgr = _make_manager()
    config = await mgr.get_spread(CurrencyPair("GBP", "JPY"))
    assert config.base_spread_bps == 30


@pytest.mark.asyncio
async def test_set_spread_upserts():
    mgr = _make_manager()
    pair = CurrencyPair("GBP", "EUR")
    new_config = SpreadConfig(
        pair=pair,
        base_spread_bps=15,
        min_spread_bps=5,
        vip_spread_bps=7,
        tier_volume_threshold=Decimal("50000"),
    )
    result = await mgr.set_spread(pair, new_config)
    assert result.base_spread_bps == 15
    retrieved = await mgr.get_spread(pair)
    assert retrieved.base_spread_bps == 15


@pytest.mark.asyncio
async def test_get_effective_spread_normal_entity():
    mgr = _make_manager()
    pair = CurrencyPair("GBP", "EUR")
    spread = await mgr.get_effective_spread(pair, "regular-entity", Decimal("1000"))
    assert spread == 20


@pytest.mark.asyncio
async def test_get_effective_spread_vip_entity():
    mgr = _make_manager()
    pair = CurrencyPair("GBP", "EUR")
    spread = await mgr.get_effective_spread(pair, "vip-client-001", Decimal("1000"))
    # vip_spread_bps for GBP/EUR = 10
    assert spread == 10


@pytest.mark.asyncio
async def test_get_effective_spread_vip_prefix_detection():
    mgr = _make_manager()
    pair = CurrencyPair("GBP", "USD")
    spread = await mgr.get_effective_spread(pair, "vip-hedge-fund", Decimal("500"))
    assert spread == 10  # vip_spread_bps


@pytest.mark.asyncio
async def test_get_effective_spread_high_volume():
    mgr = _make_manager()
    pair = CurrencyPair("GBP", "EUR")
    # GBP/EUR tier_volume_threshold = 100000
    spread = await mgr.get_effective_spread(pair, "regular-entity", Decimal("100000"))
    assert spread == 8  # min_spread_bps


@pytest.mark.asyncio
async def test_get_effective_spread_volume_below_tier():
    mgr = _make_manager()
    pair = CurrencyPair("GBP", "EUR")
    spread = await mgr.get_effective_spread(pair, "regular-entity", Decimal("99999"))
    assert spread == 20  # base_spread_bps


@pytest.mark.asyncio
async def test_get_effective_spread_vip_overrides_volume():
    mgr = _make_manager()
    pair = CurrencyPair("GBP", "EUR")
    # VIP + high volume → VIP wins (checked first)
    spread = await mgr.get_effective_spread(pair, "vip-big-trader", Decimal("200000"))
    assert spread == 10  # vip_spread_bps, not min_spread_bps


@pytest.mark.asyncio
async def test_list_spreads_returns_all_default():
    mgr = _make_manager()
    spreads = await mgr.list_spreads()
    assert len(spreads) == 6


@pytest.mark.asyncio
async def test_list_spreads_includes_new_config():
    mgr = _make_manager()
    pair = CurrencyPair("GBP", "JPY")
    new_config = SpreadConfig(
        pair=pair,
        base_spread_bps=80,
        min_spread_bps=40,
        vip_spread_bps=50,
        tier_volume_threshold=Decimal("200000"),
    )
    await mgr.set_spread(pair, new_config)
    spreads = await mgr.list_spreads()
    pair_strs = [str(c.pair) for c in spreads]
    assert "GBP/JPY" in pair_strs
