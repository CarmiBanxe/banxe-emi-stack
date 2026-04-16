"""tests/test_fx_exchange/test_rate_provider.py — RateProvider tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.fx_exchange.models import (
    _SUPPORTED_PAIRS,
    CurrencyPair,
    InMemoryRateStore,
    RateSource,
)
from services.fx_exchange.rate_provider import RateProvider


def _make_provider() -> tuple[RateProvider, InMemoryRateStore]:
    store = InMemoryRateStore()
    provider = RateProvider(store)
    return provider, store


@pytest.mark.asyncio
async def test_refresh_rates_returns_all_supported():
    provider, _ = _make_provider()
    snapshots = await provider.refresh_rates(list(_SUPPORTED_PAIRS))
    assert len(snapshots) == 6


@pytest.mark.asyncio
async def test_refresh_rates_gbp_eur_realistic():
    provider, _ = _make_provider()
    pair = CurrencyPair("GBP", "EUR")
    snapshots = await provider.refresh_rates([pair])
    assert len(snapshots) == 1
    assert snapshots[0].rate == Decimal("1.17")


@pytest.mark.asyncio
async def test_refresh_rates_gbp_usd_realistic():
    provider, _ = _make_provider()
    pair = CurrencyPair("GBP", "USD")
    snapshots = await provider.refresh_rates([pair])
    assert snapshots[0].rate == Decimal("1.27")


@pytest.mark.asyncio
async def test_refresh_rates_gbp_chf_realistic():
    provider, _ = _make_provider()
    pair = CurrencyPair("GBP", "CHF")
    snapshots = await provider.refresh_rates([pair])
    assert snapshots[0].rate == Decimal("1.13")


@pytest.mark.asyncio
async def test_refresh_rates_gbp_pln_realistic():
    provider, _ = _make_provider()
    pair = CurrencyPair("GBP", "PLN")
    snapshots = await provider.refresh_rates([pair])
    assert snapshots[0].rate == Decimal("5.05")


@pytest.mark.asyncio
async def test_refresh_rates_gbp_czk_realistic():
    provider, _ = _make_provider()
    pair = CurrencyPair("GBP", "CZK")
    snapshots = await provider.refresh_rates([pair])
    assert snapshots[0].rate == Decimal("29.5")


@pytest.mark.asyncio
async def test_refresh_rates_eur_usd_realistic():
    provider, _ = _make_provider()
    pair = CurrencyPair("EUR", "USD")
    snapshots = await provider.refresh_rates([pair])
    assert snapshots[0].rate == Decimal("1.08")


@pytest.mark.asyncio
async def test_refresh_rates_source_is_ecb():
    provider, _ = _make_provider()
    pair = CurrencyPair("GBP", "EUR")
    snapshots = await provider.refresh_rates([pair])
    assert snapshots[0].source == RateSource.ECB


@pytest.mark.asyncio
async def test_refresh_rates_rate_is_decimal():
    provider, _ = _make_provider()
    pair = CurrencyPair("GBP", "EUR")
    snapshots = await provider.refresh_rates([pair])
    assert isinstance(snapshots[0].rate, Decimal)


@pytest.mark.asyncio
async def test_get_rate_after_refresh():
    provider, _ = _make_provider()
    pair = CurrencyPair("GBP", "EUR")
    await provider.refresh_rates([pair])
    snap = await provider.get_rate(pair)
    assert snap.rate == Decimal("1.17")


@pytest.mark.asyncio
async def test_get_rate_auto_seeds_on_first_access():
    provider, _ = _make_provider()
    pair = CurrencyPair("GBP", "USD")
    snap = await provider.get_rate(pair)
    assert snap.rate == Decimal("1.27")
    assert snap.source == RateSource.FALLBACK


@pytest.mark.asyncio
async def test_get_rate_unsupported_pair_raises():
    provider, _ = _make_provider()
    pair = CurrencyPair("GBP", "JPY")  # not in seed
    with pytest.raises(ValueError, match="Unsupported currency pair"):
        await provider.get_rate(pair)


@pytest.mark.asyncio
async def test_get_all_rates_after_refresh():
    provider, _ = _make_provider()
    await provider.refresh_rates(list(_SUPPORTED_PAIRS))
    all_rates = await provider.get_all_rates()
    assert len(all_rates) == 6


@pytest.mark.asyncio
async def test_get_all_rates_empty_before_refresh():
    provider, _ = _make_provider()
    all_rates = await provider.get_all_rates()
    assert all_rates == []


@pytest.mark.asyncio
async def test_rate_history_grows_on_multiple_refreshes():
    provider, _ = _make_provider()
    pair = CurrencyPair("GBP", "EUR")
    await provider.refresh_rates([pair])
    await provider.refresh_rates([pair])
    history = await provider.get_rate_history(pair)
    assert len(history) == 2


@pytest.mark.asyncio
async def test_rate_history_limit_respected():
    provider, _ = _make_provider()
    pair = CurrencyPair("GBP", "EUR")
    for _ in range(10):
        await provider.refresh_rates([pair])
    history = await provider.get_rate_history(pair, limit=5)
    assert len(history) == 5


@pytest.mark.asyncio
async def test_rate_history_empty_for_unknown_pair():
    provider, _ = _make_provider()
    pair = CurrencyPair("GBP", "EUR")
    history = await provider.get_rate_history(pair)
    assert history == []


@pytest.mark.asyncio
async def test_refresh_rates_timestamps_are_timezone_aware():
    provider, _ = _make_provider()
    pair = CurrencyPair("GBP", "EUR")
    snapshots = await provider.refresh_rates([pair])
    assert snapshots[0].timestamp.tzinfo is not None
