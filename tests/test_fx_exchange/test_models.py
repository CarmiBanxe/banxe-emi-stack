"""tests/test_fx_exchange/test_models.py — Models, enums, seed data tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from services.fx_exchange.models import (
    _DEFAULT_SPREADS,
    _SUPPORTED_PAIRS,
    ComplianceFlag,
    CurrencyPair,
    FXOrder,
    FXOrderStatus,
    FXOrderType,
    FXQuote,
    InMemoryFXAudit,
    InMemoryQuoteStore,
    InMemoryRateStore,
    RateSnapshot,
    RateSource,
    get_default_spread_config,
)

# ── Enum tests ────────────────────────────────────────────────────────────────


def test_rate_source_ecb():
    assert RateSource.ECB == "ECB"


def test_rate_source_frankfurter():
    assert RateSource.FRANKFURTER == "FRANKFURTER"


def test_rate_source_fallback():
    assert RateSource.FALLBACK == "FALLBACK"


def test_fx_order_status_values():
    assert FXOrderStatus.PENDING == "PENDING"
    assert FXOrderStatus.EXECUTED == "EXECUTED"
    assert FXOrderStatus.FAILED == "FAILED"
    assert FXOrderStatus.EXPIRED == "EXPIRED"


def test_fx_order_type_values():
    assert FXOrderType.SPOT == "SPOT"
    assert FXOrderType.FORWARD == "FORWARD"


def test_compliance_flag_values():
    assert ComplianceFlag.CLEAR == "CLEAR"
    assert ComplianceFlag.EDD_REQUIRED == "EDD_REQUIRED"
    assert ComplianceFlag.BLOCKED == "BLOCKED"


# ── CurrencyPair dataclass tests ───────────────────────────────────────────────


def test_currency_pair_equality():
    p1 = CurrencyPair("GBP", "EUR")
    p2 = CurrencyPair("GBP", "EUR")
    assert p1 == p2


def test_currency_pair_inequality():
    assert CurrencyPair("GBP", "EUR") != CurrencyPair("GBP", "USD")


def test_currency_pair_str():
    pair = CurrencyPair("GBP", "EUR")
    assert str(pair) == "GBP/EUR"


def test_currency_pair_frozen():
    pair = CurrencyPair("GBP", "EUR")
    with pytest.raises(AttributeError):
        pair.base = "USD"  # type: ignore[misc]


def test_currency_pair_hashable():
    pair = CurrencyPair("GBP", "EUR")
    d = {pair: "test"}
    assert d[pair] == "test"


# ── FXQuote dataclass ─────────────────────────────────────────────────────────


def test_fx_quote_frozen():
    now = datetime.now(UTC)
    q = FXQuote(
        quote_id="q1",
        pair=CurrencyPair("GBP", "EUR"),
        rate=Decimal("1.17"),
        bid=Decimal("1.169"),
        ask=Decimal("1.171"),
        spread_bps=20,
        source=RateSource.ECB,
        valid_until=now,
        created_at=now,
    )
    with pytest.raises(AttributeError):
        q.rate = Decimal("1.20")  # type: ignore[misc]


def test_fx_quote_bid_less_than_ask():
    now = datetime.now(UTC)
    q = FXQuote(
        quote_id="q1",
        pair=CurrencyPair("GBP", "EUR"),
        rate=Decimal("1.17"),
        bid=Decimal("1.169"),
        ask=Decimal("1.171"),
        spread_bps=20,
        source=RateSource.ECB,
        valid_until=now,
        created_at=now,
    )
    assert q.bid < q.ask


def test_fx_quote_rate_is_decimal():
    now = datetime.now(UTC)
    q = FXQuote(
        quote_id="q1",
        pair=CurrencyPair("GBP", "EUR"),
        rate=Decimal("1.17"),
        bid=Decimal("1.169"),
        ask=Decimal("1.171"),
        spread_bps=20,
        source=RateSource.ECB,
        valid_until=now,
        created_at=now,
    )
    assert isinstance(q.rate, Decimal)
    assert isinstance(q.bid, Decimal)
    assert isinstance(q.ask, Decimal)


# ── FXOrder dataclass ─────────────────────────────────────────────────────────


def test_fx_order_defaults():
    now = datetime.now(UTC)
    order = FXOrder(
        order_id="o1",
        entity_id="ent1",
        pair=CurrencyPair("GBP", "EUR"),
        amount_base=Decimal("1000"),
        amount_quote=Decimal("1170"),
        rate=Decimal("1.17"),
        order_type=FXOrderType.SPOT,
        status=FXOrderStatus.PENDING,
        compliance_flag=ComplianceFlag.CLEAR,
        created_at=now,
    )
    assert order.executed_at is None


def test_fx_order_frozen():
    now = datetime.now(UTC)
    order = FXOrder(
        order_id="o1",
        entity_id="ent1",
        pair=CurrencyPair("GBP", "EUR"),
        amount_base=Decimal("1000"),
        amount_quote=Decimal("1170"),
        rate=Decimal("1.17"),
        order_type=FXOrderType.SPOT,
        status=FXOrderStatus.PENDING,
        compliance_flag=ComplianceFlag.CLEAR,
        created_at=now,
    )
    with pytest.raises(AttributeError):
        order.status = FXOrderStatus.EXECUTED  # type: ignore[misc]


# ── Seed data tests ───────────────────────────────────────────────────────────


def test_supported_pairs_count():
    assert len(_SUPPORTED_PAIRS) == 6


def test_supported_pairs_includes_gbp_eur():
    assert CurrencyPair("GBP", "EUR") in _SUPPORTED_PAIRS


def test_supported_pairs_includes_eur_usd():
    assert CurrencyPair("EUR", "USD") in _SUPPORTED_PAIRS


def test_default_spreads_count():
    assert len(_DEFAULT_SPREADS) == 6


def test_major_pairs_spread_20bps():
    assert _DEFAULT_SPREADS["GBP/EUR"].base_spread_bps == 20
    assert _DEFAULT_SPREADS["GBP/USD"].base_spread_bps == 20


def test_exotic_pairs_spread_50bps():
    assert _DEFAULT_SPREADS["GBP/PLN"].base_spread_bps == 50
    assert _DEFAULT_SPREADS["GBP/CZK"].base_spread_bps == 50


def test_get_default_spread_config_unknown_pair():
    pair = CurrencyPair("GBP", "JPY")
    config = get_default_spread_config(pair)
    assert config.base_spread_bps == 30
    assert config.pair == pair


# ── InMemory stubs basic functionality ────────────────────────────────────────


@pytest.mark.asyncio
async def test_inmemory_rate_store_save_and_get():
    store = InMemoryRateStore()
    pair = CurrencyPair("GBP", "EUR")
    snap = RateSnapshot(
        pair=pair, rate=Decimal("1.17"), source=RateSource.ECB, timestamp=datetime.now(UTC)
    )
    await store.save_rate(snap)
    result = await store.get_latest_rate(pair)
    assert result is not None
    assert result.rate == Decimal("1.17")


@pytest.mark.asyncio
async def test_inmemory_quote_store_save_and_get():
    store = InMemoryQuoteStore()
    now = datetime.now(UTC)
    q = FXQuote(
        quote_id="q-test",
        pair=CurrencyPair("GBP", "EUR"),
        rate=Decimal("1.17"),
        bid=Decimal("1.169"),
        ask=Decimal("1.171"),
        spread_bps=20,
        source=RateSource.ECB,
        valid_until=now,
        created_at=now,
    )
    await store.save_quote(q)
    result = await store.get_quote("q-test")
    assert result is not None
    assert result.quote_id == "q-test"


@pytest.mark.asyncio
async def test_inmemory_audit_append_only():
    audit = InMemoryFXAudit()
    await audit.log_event("test_event", {"entity_id": "ent1", "value": "x"})
    await audit.log_event("test_event2", {"entity_id": "ent1", "value": "y"})
    events = await audit.list_events("ent1")
    assert len(events) == 2
