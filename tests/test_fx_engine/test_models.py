"""
Tests for FX Engine models.
IL-FXE-01 | Sprint 34 | Phase 48
Tests: pydantic v2 validators, TTL ≤30, Decimal fields (I-22)
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import ValidationError
import pytest

from services.fx_engine.models import (
    ExecutionStatus,
    FXExecution,
    FXQuote,
    FXRate,
    FXRateType,
    HedgePosition,
    HITLProposal,
    InMemoryExecutionStore,
    InMemoryHedgeStore,
    InMemoryQuoteStore,
    InMemoryRateStore,
    QuoteStatus,
)


def make_rate(**kwargs):
    defaults = dict(
        rate_id="r_001",
        currency_pair="GBP/EUR",
        base_currency="GBP",
        quote_currency="EUR",
        bid=Decimal("1.1650"),
        ask=Decimal("1.1680"),
        mid=Decimal("1.1665"),
        timestamp="2026-04-20T00:00:00+00:00",
    )
    defaults.update(kwargs)
    return FXRate(**defaults)


def make_quote(**kwargs):
    defaults = dict(
        quote_id="qte_001",
        currency_pair="GBP/EUR",
        sell_amount=Decimal("1000"),
        sell_currency="GBP",
        buy_amount=Decimal("1160"),
        buy_currency="EUR",
        rate=Decimal("1.1600"),
        spread=Decimal("0.005"),
        ttl_seconds=30,
        created_at="2026-04-20T00:00:00+00:00",
        expires_at="2026-04-20T00:00:30+00:00",
    )
    defaults.update(kwargs)
    return FXQuote(**defaults)


class TestFXRate:
    def test_valid_rate(self):
        rate = make_rate()
        assert rate.currency_pair == "GBP/EUR"
        assert rate.bid == Decimal("1.1650")

    def test_bid_is_decimal(self):
        rate = make_rate()
        assert isinstance(rate.bid, Decimal)
        assert isinstance(rate.ask, Decimal)
        assert isinstance(rate.mid, Decimal)

    def test_not_stale_by_default(self):
        rate = make_rate()
        assert rate.is_stale is False

    def test_rate_type_default_spot(self):
        rate = make_rate()
        assert rate.rate_type == FXRateType.SPOT

    def test_provider_default_internal(self):
        rate = make_rate()
        assert rate.provider == "internal"


class TestFXQuote:
    def test_valid_quote(self):
        quote = make_quote()
        assert quote.quote_id == "qte_001"
        assert quote.status == QuoteStatus.ACTIVE

    def test_ttl_30_valid(self):
        quote = make_quote(ttl_seconds=30)
        assert quote.ttl_seconds == 30

    def test_ttl_over_30_raises(self):
        with pytest.raises(ValidationError):
            make_quote(ttl_seconds=31)

    def test_ttl_1_valid(self):
        quote = make_quote(ttl_seconds=1)
        assert quote.ttl_seconds == 1

    def test_sell_amount_is_decimal(self):
        quote = make_quote()
        assert isinstance(quote.sell_amount, Decimal)

    def test_buy_amount_is_decimal(self):
        quote = make_quote()
        assert isinstance(quote.buy_amount, Decimal)

    def test_rate_is_decimal(self):
        quote = make_quote()
        assert isinstance(quote.rate, Decimal)

    def test_spread_is_decimal(self):
        quote = make_quote()
        assert isinstance(quote.spread, Decimal)

    def test_status_default_active(self):
        quote = make_quote()
        assert quote.status == QuoteStatus.ACTIVE

    def test_tenant_id_default(self):
        quote = make_quote()
        assert quote.tenant_id == "default"


class TestFXExecution:
    def test_valid_execution(self):
        exe = FXExecution(
            execution_id="exe_001",
            quote_id="qte_001",
            status=ExecutionStatus.CONFIRMED,
        )
        assert exe.status == ExecutionStatus.CONFIRMED

    def test_execution_pending_status(self):
        exe = FXExecution(
            execution_id="exe_002",
            quote_id="qte_001",
            status=ExecutionStatus.PENDING,
        )
        assert exe.status == ExecutionStatus.PENDING


class TestHedgePosition:
    def test_valid_position(self):
        pos = HedgePosition(
            position_id="hp_001",
            currency_pair="GBP/EUR",
            net_long=Decimal("100000"),
            net_short=Decimal("80000"),
            net_exposure=Decimal("20000"),
            snapshot_date="2026-04-20T00:00:00+00:00",
        )
        assert pos.net_exposure == Decimal("20000")

    def test_amounts_are_decimal(self):
        pos = HedgePosition(
            position_id="hp_001",
            currency_pair="GBP/EUR",
            net_long=Decimal("100000"),
            net_short=Decimal("80000"),
            net_exposure=Decimal("20000"),
            snapshot_date="2026-04-20T00:00:00+00:00",
        )
        assert isinstance(pos.net_long, Decimal)
        assert isinstance(pos.net_short, Decimal)
        assert isinstance(pos.net_exposure, Decimal)


class TestInMemoryStores:
    def test_rate_store_seeded(self):
        store = InMemoryRateStore()
        assert store.get_latest("GBP/EUR") is not None
        assert store.get_latest("GBP/USD") is not None
        assert store.get_latest("EUR/USD") is not None

    def test_rate_store_get_all(self):
        store = InMemoryRateStore()
        rates = store.get_all()
        assert len(rates) >= 3

    def test_quote_store_save_get(self):
        store = InMemoryQuoteStore()
        quote = make_quote()
        store.save(quote)
        assert store.get("qte_001") == quote

    def test_execution_store_append_only(self):
        store = InMemoryExecutionStore()
        exe = FXExecution(
            execution_id="exe_a",
            quote_id="qte_001",
            status=ExecutionStatus.CONFIRMED,
        )
        store.append(exe)
        assert store.get("exe_a") is not None

    def test_hedge_store_append_latest(self):
        store = InMemoryHedgeStore()
        pos = HedgePosition(
            position_id="hp_1",
            currency_pair="GBP/EUR",
            net_long=Decimal("1000"),
            net_short=Decimal("0"),
            net_exposure=Decimal("1000"),
            snapshot_date="2026-04-20T00:00:00+00:00",
        )
        store.append(pos)
        assert store.get_latest("GBP/EUR") is not None

    def test_hitl_proposal_fields(self):
        proposal = HITLProposal(
            action="EXECUTE_LARGE_FX",
            quote_id="qte_001",
            requires_approval_from="TREASURY_OPS",
            reason="test",
        )
        assert proposal.autonomy_level == "L4"
