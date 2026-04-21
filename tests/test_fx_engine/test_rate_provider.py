"""
Tests for FX Rate Provider.
IL-FXE-01 | Sprint 34 | Phase 48
Tests: staleness check, Decimal bid/ask/mid (I-22), stale flag, BT-004 NotImplementedError
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from services.fx_engine.models import InMemoryRateStore
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


class TestLiveRateProvider:
    def test_get_rate_raises_not_implemented(self):
        live = LiveRateProvider()
        with pytest.raises(NotImplementedError, match="BT-004"):
            live.get_rate("GBP/EUR")

    def test_get_all_rates_raises_not_implemented(self):
        live = LiveRateProvider()
        with pytest.raises(NotImplementedError, match="BT-004"):
            live.get_all_rates()

    def test_update_rate_raises_not_implemented(self):
        live = LiveRateProvider()
        with pytest.raises(NotImplementedError, match="BT-004"):
            live.update_rate("GBP/EUR", Decimal("1.16"), Decimal("1.17"))

    def test_get_bid_raises_not_implemented(self):
        live = LiveRateProvider()
        with pytest.raises(NotImplementedError, match="BT-004"):
            live.get_bid("GBP/EUR")

    def test_check_staleness_raises_not_implemented(self):
        live = LiveRateProvider()
        with pytest.raises(NotImplementedError, match="BT-004"):
            live.check_staleness("GBP/EUR")
