"""
Tests for FX Rate Provider.
IL-FXE-01 | Sprint 34 | Phase 48
Tests: staleness check, Decimal bid/ask/mid (I-22), stale flag, BT-004 live ECB feed.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from services.fx_engine.models import FXRate, InMemoryRateStore
from services.fx_engine.rate_provider import (
    STALE_THRESHOLD_SECONDS,
    LiveRateProvider,
    RateProvider,
)


@pytest.fixture
def provider():
    return RateProvider(store=InMemoryRateStore())


class TestGetRate:
    def test_get_existing_rate(self, provider):
        rate = provider.get_rate("GBP/EUR")
        assert rate is not None
        assert rate.currency_pair == "GBP/EUR"

    def test_get_nonexistent_rate_none(self, provider):
        rate = provider.get_rate("GBP/JPY")
        assert rate is None

    def test_fresh_rate_not_stale(self, provider):
        rate = provider.get_rate("GBP/EUR")
        assert rate.is_stale is False

    def test_stale_rate_marked_stale(self, provider):
        store = InMemoryRateStore()
        old_ts = (datetime.now(UTC) - timedelta(seconds=120)).isoformat()
        store._data["GBP/EUR"] = store._data["GBP/EUR"].model_copy(update={"timestamp": old_ts})
        prov = RateProvider(store=store)
        rate = prov.get_rate("GBP/EUR")
        assert rate.is_stale is True


class TestGetAllRates:
    def test_get_all_returns_list(self, provider):
        rates = provider.get_all_rates()
        assert isinstance(rates, list)

    def test_get_all_has_seeded_rates(self, provider):
        rates = provider.get_all_rates()
        pairs = [r.currency_pair for r in rates]
        assert "GBP/EUR" in pairs
        assert "GBP/USD" in pairs
        assert "EUR/USD" in pairs


class TestUpdateRate:
    def test_update_rate_sets_mid(self, provider):
        rate = provider.update_rate("GBP/EUR", Decimal("1.16"), Decimal("1.17"))
        assert rate.mid == Decimal("1.165")

    def test_update_rate_mid_is_decimal(self, provider):
        rate = provider.update_rate("GBP/EUR", Decimal("1.20"), Decimal("1.22"))
        assert isinstance(rate.mid, Decimal)

    def test_update_rate_timestamp_utc(self, provider):
        rate = provider.update_rate("GBP/EUR", Decimal("1.16"), Decimal("1.17"))
        assert rate.timestamp  # Non-empty UTC

    def test_update_rate_not_stale(self, provider):
        rate = provider.update_rate("GBP/EUR", Decimal("1.16"), Decimal("1.17"))
        assert rate.is_stale is False

    def test_update_new_pair(self, provider):
        rate = provider.update_rate("GBP/CHF", Decimal("1.10"), Decimal("1.12"))
        assert rate.currency_pair == "GBP/CHF"


class TestCheckStaleness:
    def test_fresh_rate_not_stale(self, provider):
        assert provider.check_staleness("GBP/EUR") is False

    def test_stale_rate_is_stale(self, provider):
        store = InMemoryRateStore()
        old_ts = (datetime.now(UTC) - timedelta(seconds=120)).isoformat()
        store._data["GBP/EUR"] = store._data["GBP/EUR"].model_copy(update={"timestamp": old_ts})
        prov = RateProvider(store=store)
        assert prov.check_staleness("GBP/EUR") is True

    def test_unknown_pair_is_stale(self, provider):
        assert provider.check_staleness("XYZ/ABC") is True

    def test_stale_threshold_60s(self):
        assert STALE_THRESHOLD_SECONDS == 60


class TestGetBidAskMid:
    def test_get_bid_is_decimal(self, provider):
        bid = provider.get_bid("GBP/EUR")
        assert isinstance(bid, Decimal)

    def test_get_ask_is_decimal(self, provider):
        ask = provider.get_ask("GBP/EUR")
        assert isinstance(ask, Decimal)

    def test_get_mid_is_decimal(self, provider):
        mid = provider.get_mid("GBP/EUR")
        assert isinstance(mid, Decimal)

    def test_get_bid_none_unknown(self, provider):
        bid = provider.get_bid("XYZ/ABC")
        assert bid is None

    def test_bid_less_than_ask(self, provider):
        bid = provider.get_bid("GBP/EUR")
        ask = provider.get_ask("GBP/EUR")
        assert bid < ask

    def test_mid_between_bid_and_ask(self, provider):
        bid = provider.get_bid("GBP/EUR")
        ask = provider.get_ask("GBP/EUR")
        mid = provider.get_mid("GBP/EUR")
        assert bid < mid < ask


def _mock_feed(rates: dict[str, Decimal]) -> MagicMock:
    feed = MagicMock()
    feed.get_latest.return_value = rates
    return feed


def _live(rates: dict[str, Decimal]) -> LiveRateProvider:
    return LiveRateProvider(feed=_mock_feed(rates), store=InMemoryRateStore())


class TestLiveRateProvider:
    def test_get_rate_returns_fx_rate(self):
        live = _live({"EUR": Decimal("1.1665")})
        rate = live.get_rate("GBP/EUR")
        assert isinstance(rate, FXRate)

    def test_get_rate_currency_pair_set(self):
        live = _live({"EUR": Decimal("1.1665")})
        rate = live.get_rate("GBP/EUR")
        assert rate is not None
        assert rate.currency_pair == "GBP/EUR"

    def test_get_rate_mid_is_decimal(self):
        live = _live({"EUR": Decimal("1.1665")})
        rate = live.get_rate("GBP/EUR")
        assert rate is not None
        assert isinstance(rate.mid, Decimal)

    def test_get_rate_provider_is_frankfurter_ecb(self):
        # Use GBP/JPY — not seeded in InMemoryRateStore
        live = LiveRateProvider(
            feed=_mock_feed({"JPY": Decimal("195.50")}), store=InMemoryRateStore()
        )
        rate = live.get_rate("GBP/JPY")
        assert rate is not None
        assert rate.provider == "frankfurter_ecb"

    def test_get_rate_none_when_quote_not_in_response(self):
        # Use GBP/JPY — not seeded; feed returns empty → None
        live = LiveRateProvider(feed=_mock_feed({}), store=InMemoryRateStore())
        rate = live.get_rate("GBP/JPY")
        assert rate is None

    def test_get_rate_none_on_feed_exception(self):
        # Use GBP/JPY — not seeded; feed throws → None
        feed = MagicMock()
        feed.get_latest.side_effect = RuntimeError("Frankfurter down")
        live = LiveRateProvider(feed=feed, store=InMemoryRateStore())
        rate = live.get_rate("GBP/JPY")
        assert rate is None

    def test_get_rate_uses_cache_when_fresh(self):
        # Use GBP/JPY — not seeded; first call fetches, second uses cache
        feed = _mock_feed({"JPY": Decimal("195.50")})
        live = LiveRateProvider(feed=feed, store=InMemoryRateStore())
        live.get_rate("GBP/JPY")
        live.get_rate("GBP/JPY")
        assert feed.get_latest.call_count == 1

    def test_get_rate_refetches_when_stale(self):
        store = InMemoryRateStore()
        feed = _mock_feed({"EUR": Decimal("1.1665")})
        live = LiveRateProvider(feed=feed, store=store)
        # Prime cache with stale timestamp
        stale_ts = (datetime.now(UTC) - timedelta(seconds=120)).isoformat()
        stale = FXRate(
            rate_id="live_gbp_eur",
            currency_pair="GBP/EUR",
            base_currency="GBP",
            quote_currency="EUR",
            bid=Decimal("1.16"),
            ask=Decimal("1.16"),
            mid=Decimal("1.16"),
            timestamp=stale_ts,
            provider="frankfurter_ecb",
            is_stale=True,
        )
        store.save(stale)
        live.get_rate("GBP/EUR")
        assert feed.get_latest.call_count == 1

    def test_get_all_rates_returns_list(self):
        live = _live({"EUR": Decimal("1.1665")})
        live.get_rate("GBP/EUR")
        assert isinstance(live.get_all_rates(), list)

    def test_get_all_rates_includes_fetched(self):
        live = _live({"EUR": Decimal("1.1665")})
        live.get_rate("GBP/EUR")
        pairs = [r.currency_pair for r in live.get_all_rates()]
        assert "GBP/EUR" in pairs

    def test_update_rate_stores_mid(self):
        live = LiveRateProvider(feed=_mock_feed({}), store=InMemoryRateStore())
        rate = live.update_rate("GBP/USD", Decimal("1.26"), Decimal("1.28"))
        assert rate.mid == Decimal("1.27")

    def test_update_rate_mid_is_decimal(self):
        live = LiveRateProvider(feed=_mock_feed({}), store=InMemoryRateStore())
        rate = live.update_rate("GBP/USD", Decimal("1.26"), Decimal("1.28"))
        assert isinstance(rate.mid, Decimal)

    def test_update_rate_is_not_stale(self):
        live = LiveRateProvider(feed=_mock_feed({}), store=InMemoryRateStore())
        rate = live.update_rate("GBP/USD", Decimal("1.26"), Decimal("1.28"))
        assert rate.is_stale is False

    def test_check_staleness_true_when_not_found(self):
        live = LiveRateProvider(feed=_mock_feed({}), store=InMemoryRateStore())
        assert live.check_staleness("GBP/CHF") is True

    def test_check_staleness_false_when_fresh(self):
        live = _live({"EUR": Decimal("1.1665")})
        live.get_rate("GBP/EUR")
        assert live.check_staleness("GBP/EUR") is False

    def test_check_staleness_true_when_stale(self):
        store = InMemoryRateStore()
        stale_ts = (datetime.now(UTC) - timedelta(seconds=120)).isoformat()
        stale = FXRate(
            rate_id="live_gbp_eur",
            currency_pair="GBP/EUR",
            base_currency="GBP",
            quote_currency="EUR",
            bid=Decimal("1.16"),
            ask=Decimal("1.16"),
            mid=Decimal("1.16"),
            timestamp=stale_ts,
            provider="frankfurter_ecb",
            is_stale=True,
        )
        store.save(stale)
        live = LiveRateProvider(feed=_mock_feed({}), store=store)
        assert live.check_staleness("GBP/EUR") is True

    def test_get_bid_returns_decimal(self):
        live = _live({"EUR": Decimal("1.1665")})
        bid = live.get_bid("GBP/EUR")
        assert isinstance(bid, Decimal)

    def test_get_ask_returns_decimal(self):
        live = _live({"EUR": Decimal("1.1665")})
        ask = live.get_ask("GBP/EUR")
        assert isinstance(ask, Decimal)

    def test_get_mid_returns_decimal(self):
        live = _live({"EUR": Decimal("1.1665")})
        mid = live.get_mid("GBP/EUR")
        assert isinstance(mid, Decimal)

    def test_get_bid_none_for_unknown_pair(self):
        live = LiveRateProvider(feed=_mock_feed({}), store=InMemoryRateStore())
        assert live.get_bid("XYZ/ABC") is None
