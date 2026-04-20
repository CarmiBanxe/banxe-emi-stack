"""
Tests for FX Quoter.
IL-FXE-01 | Sprint 34 | Phase 48
Tests: quote creation, TTL expiry, I-23 UTC timestamps, no rate → None
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from services.fx_engine.fx_quoter import FXQuoter
from services.fx_engine.models import (
    InMemoryQuoteStore,
    InMemoryRateStore,
    QuoteStatus,
)


@pytest.fixture
def quoter():
    return FXQuoter(
        rate_store=InMemoryRateStore(),
        quote_store=InMemoryQuoteStore(),
    )


class TestCreateQuote:
    def test_create_quote_basic(self, quoter):
        quote = quoter.create_quote("GBP/EUR", Decimal("1000"), "GBP")
        assert quote is not None
        assert quote.currency_pair == "GBP/EUR"
        assert quote.status == QuoteStatus.ACTIVE

    def test_create_quote_id_starts_with_qte(self, quoter):
        quote = quoter.create_quote("GBP/EUR", Decimal("1000"), "GBP")
        assert quote.quote_id.startswith("qte_")

    def test_create_quote_sell_amount_decimal(self, quoter):
        quote = quoter.create_quote("GBP/EUR", Decimal("5000"), "GBP")
        assert isinstance(quote.sell_amount, Decimal)

    def test_create_quote_buy_amount_decimal(self, quoter):
        quote = quoter.create_quote("GBP/EUR", Decimal("1000"), "GBP")
        assert isinstance(quote.buy_amount, Decimal)

    def test_create_quote_buy_currency_eur(self, quoter):
        quote = quoter.create_quote("GBP/EUR", Decimal("1000"), "GBP")
        assert quote.buy_currency == "EUR"

    def test_create_quote_ttl_30s(self, quoter):
        quote = quoter.create_quote("GBP/EUR", Decimal("1000"), "GBP")
        assert quote.ttl_seconds == 30

    def test_create_quote_expires_at_utc(self, quoter):
        quote = quoter.create_quote("GBP/EUR", Decimal("1000"), "GBP")
        created = datetime.fromisoformat(quote.created_at)
        expires = datetime.fromisoformat(quote.expires_at)
        diff = (expires - created).total_seconds()
        assert abs(diff - 30) < 1  # ~30 seconds TTL

    def test_create_quote_no_rate_returns_none(self, quoter):
        quote = quoter.create_quote("GBP/JPY", Decimal("1000"), "GBP")
        assert quote is None

    def test_create_quote_spread_applied(self, quoter):
        quote = quoter.create_quote("GBP/EUR", Decimal("1000"), "GBP")
        assert quote.spread > Decimal("0")

    def test_create_quote_usd_pair(self, quoter):
        quote = quoter.create_quote("GBP/USD", Decimal("2000"), "GBP")
        assert quote is not None
        assert quote.buy_currency == "USD"

    def test_create_quote_tenant_id(self, quoter):
        quote = quoter.create_quote("GBP/EUR", Decimal("1000"), "GBP", tenant_id="t_123")
        assert quote.tenant_id == "t_123"


class TestGetQuote:
    def test_get_existing_quote(self, quoter):
        created = quoter.create_quote("GBP/EUR", Decimal("1000"), "GBP")
        fetched = quoter.get_quote(created.quote_id)
        assert fetched is not None
        assert fetched.quote_id == created.quote_id

    def test_get_nonexistent_quote_none(self, quoter):
        assert quoter.get_quote("nonexistent") is None


class TestIsQuoteValid:
    def test_fresh_quote_is_valid(self, quoter):
        quote = quoter.create_quote("GBP/EUR", Decimal("1000"), "GBP")
        assert quoter.is_quote_valid(quote.quote_id) is True

    def test_nonexistent_quote_invalid(self, quoter):
        assert quoter.is_quote_valid("nonexistent") is False

    def test_expired_quote_invalid(self, quoter):
        store = InMemoryQuoteStore()
        q = quoter.create_quote("GBP/EUR", Decimal("1000"), "GBP")
        # Manually expire
        old_expires = (datetime.now(UTC) - timedelta(seconds=60)).isoformat()
        updated = q.model_copy(update={"expires_at": old_expires})
        store.save(updated)
        qtr = FXQuoter(rate_store=InMemoryRateStore(), quote_store=store)
        qtr._quote_store.save(updated)
        assert qtr.is_quote_valid(q.quote_id) is False


class TestExpireQuote:
    def test_expire_quote_sets_expired_status(self, quoter):
        quote = quoter.create_quote("GBP/EUR", Decimal("1000"), "GBP")
        expired = quoter.expire_quote(quote.quote_id)
        assert expired.status == QuoteStatus.EXPIRED

    def test_expire_nonexistent_raises(self, quoter):
        with pytest.raises(ValueError):
            quoter.expire_quote("nonexistent")


class TestListActiveQuotes:
    def test_active_quotes_includes_new(self, quoter):
        quoter.create_quote("GBP/EUR", Decimal("1000"), "GBP")
        active = quoter.list_active_quotes()
        assert len(active) >= 1

    def test_expired_not_in_active(self, quoter):
        quote = quoter.create_quote("GBP/EUR", Decimal("1000"), "GBP")
        quoter.expire_quote(quote.quote_id)
        active = quoter.list_active_quotes()
        ids = [q.quote_id for q in active]
        assert quote.quote_id not in ids


class TestGetQuoteSummary:
    def test_summary_structure(self, quoter):
        summary = quoter.get_quote_summary()
        assert "active" in summary
        assert "expired" in summary
        assert "executed" in summary
        assert "rejected" in summary
