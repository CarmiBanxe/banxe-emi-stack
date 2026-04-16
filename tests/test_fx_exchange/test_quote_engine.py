"""tests/test_fx_exchange/test_quote_engine.py — QuoteEngine tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from services.fx_exchange.models import (
    CurrencyPair,
    InMemoryQuoteStore,
    InMemoryRateStore,
    RateSnapshot,
    RateSource,
)
from services.fx_exchange.quote_engine import QuoteEngine


async def _seeded_engine(
    pair: CurrencyPair = CurrencyPair("GBP", "EUR"),
    rate: Decimal = Decimal("1.17"),
) -> tuple[QuoteEngine, InMemoryRateStore, InMemoryQuoteStore]:
    rate_store = InMemoryRateStore()
    quote_store = InMemoryQuoteStore()
    snap = RateSnapshot(pair=pair, rate=rate, source=RateSource.ECB, timestamp=datetime.now(UTC))
    await rate_store.save_rate(snap)
    engine = QuoteEngine(rate_store, quote_store)
    return engine, rate_store, quote_store


@pytest.mark.asyncio
async def test_get_quote_returns_fx_quote():
    engine, _, _ = await _seeded_engine()
    quote = await engine.get_quote(CurrencyPair("GBP", "EUR"), Decimal("1000"), "ent1")
    assert quote is not None
    assert quote.quote_id != ""


@pytest.mark.asyncio
async def test_get_quote_bid_less_than_ask():
    engine, _, _ = await _seeded_engine()
    quote = await engine.get_quote(CurrencyPair("GBP", "EUR"), Decimal("1000"), "ent1")
    assert quote.bid < quote.ask


@pytest.mark.asyncio
async def test_get_quote_mid_between_bid_and_ask():
    engine, _, _ = await _seeded_engine()
    quote = await engine.get_quote(CurrencyPair("GBP", "EUR"), Decimal("1000"), "ent1")
    assert quote.bid <= quote.rate <= quote.ask


@pytest.mark.asyncio
async def test_get_quote_rate_is_decimal():
    engine, _, _ = await _seeded_engine()
    quote = await engine.get_quote(CurrencyPair("GBP", "EUR"), Decimal("1000"), "ent1")
    assert isinstance(quote.rate, Decimal)
    assert isinstance(quote.bid, Decimal)
    assert isinstance(quote.ask, Decimal)


@pytest.mark.asyncio
async def test_get_quote_spread_bps_from_config():
    engine, _, _ = await _seeded_engine()
    quote = await engine.get_quote(CurrencyPair("GBP", "EUR"), Decimal("1000"), "ent1")
    # GBP/EUR is a major pair → 20 bps
    assert quote.spread_bps == 20


@pytest.mark.asyncio
async def test_get_quote_exotic_spread_bps():
    pair = CurrencyPair("GBP", "PLN")
    engine, _, _ = await _seeded_engine(pair=pair, rate=Decimal("5.05"))
    quote = await engine.get_quote(pair, Decimal("1000"), "ent1")
    assert quote.spread_bps == 50


@pytest.mark.asyncio
async def test_get_quote_valid_until_30s_ahead():
    engine, _, _ = await _seeded_engine()
    before = datetime.now(UTC)
    quote = await engine.get_quote(CurrencyPair("GBP", "EUR"), Decimal("1000"), "ent1")
    delta = quote.valid_until - before
    assert timedelta(seconds=28) <= delta <= timedelta(seconds=32)


@pytest.mark.asyncio
async def test_get_quote_stored_in_quote_store():
    engine, _, quote_store = await _seeded_engine()
    quote = await engine.get_quote(CurrencyPair("GBP", "EUR"), Decimal("1000"), "ent1")
    stored = await quote_store.get_quote(quote.quote_id)
    assert stored is not None
    assert stored.quote_id == quote.quote_id


@pytest.mark.asyncio
async def test_validate_quote_fresh_returns_true():
    engine, _, _ = await _seeded_engine()
    quote = await engine.get_quote(CurrencyPair("GBP", "EUR"), Decimal("1000"), "ent1")
    valid = await engine.validate_quote(quote.quote_id)
    assert valid is True


@pytest.mark.asyncio
async def test_validate_quote_nonexistent_returns_false():
    engine, _, _ = await _seeded_engine()
    valid = await engine.validate_quote("nonexistent-id")
    assert valid is False


@pytest.mark.asyncio
async def test_validate_quote_expired_returns_false():
    rate_store = InMemoryRateStore()
    quote_store = InMemoryQuoteStore()
    pair = CurrencyPair("GBP", "EUR")
    snap = RateSnapshot(
        pair=pair, rate=Decimal("1.17"), source=RateSource.ECB, timestamp=datetime.now(UTC)
    )
    await rate_store.save_rate(snap)
    engine = QuoteEngine(rate_store, quote_store)
    quote = await engine.get_quote(pair, Decimal("1000"), "ent1")

    # Manually expire the quote by replacing in store with expired valid_until
    from dataclasses import replace

    expired_quote = replace(quote, valid_until=datetime.now(UTC) - timedelta(seconds=60))
    await quote_store.save_quote(expired_quote)
    valid = await engine.validate_quote(quote.quote_id)
    assert valid is False


@pytest.mark.asyncio
async def test_get_quote_by_id_returns_quote():
    engine, _, _ = await _seeded_engine()
    quote = await engine.get_quote(CurrencyPair("GBP", "EUR"), Decimal("1000"), "ent1")
    result = await engine.get_quote_by_id(quote.quote_id)
    assert result is not None
    assert result.quote_id == quote.quote_id


@pytest.mark.asyncio
async def test_get_quote_by_id_nonexistent_returns_none():
    engine, _, _ = await _seeded_engine()
    result = await engine.get_quote_by_id("does-not-exist")
    assert result is None


@pytest.mark.asyncio
async def test_get_quote_no_rate_raises():
    rate_store = InMemoryRateStore()
    quote_store = InMemoryQuoteStore()
    engine = QuoteEngine(rate_store, quote_store)
    with pytest.raises(ValueError, match="No rate available"):
        await engine.get_quote(CurrencyPair("GBP", "EUR"), Decimal("1000"), "ent1")


@pytest.mark.asyncio
async def test_get_quote_ask_above_mid():
    engine, _, _ = await _seeded_engine()
    quote = await engine.get_quote(CurrencyPair("GBP", "EUR"), Decimal("1000"), "ent1")
    assert quote.ask > quote.rate


@pytest.mark.asyncio
async def test_get_quote_bid_below_mid():
    engine, _, _ = await _seeded_engine()
    quote = await engine.get_quote(CurrencyPair("GBP", "EUR"), Decimal("1000"), "ent1")
    assert quote.bid < quote.rate


@pytest.mark.asyncio
async def test_get_quote_default_spread_for_unknown_pair():
    pair = CurrencyPair("GBP", "JPY")
    rate_store = InMemoryRateStore()
    quote_store = InMemoryQuoteStore()
    snap = RateSnapshot(
        pair=pair, rate=Decimal("180.00"), source=RateSource.FALLBACK, timestamp=datetime.now(UTC)
    )
    await rate_store.save_rate(snap)
    engine = QuoteEngine(rate_store, quote_store)
    quote = await engine.get_quote(pair, Decimal("1000"), "ent1")
    # Unknown pair → default 30 bps
    assert quote.spread_bps == 30


@pytest.mark.asyncio
async def test_get_quote_created_at_is_timezone_aware():
    engine, _, _ = await _seeded_engine()
    quote = await engine.get_quote(CurrencyPair("GBP", "EUR"), Decimal("1000"), "ent1")
    assert quote.created_at.tzinfo is not None
