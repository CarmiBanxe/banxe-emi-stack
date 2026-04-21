"""
services/fx_engine/fx_quoter.py
FX Quoter — Quote Generation
IL-FXE-01 | Sprint 34 | Phase 48

FCA: FCA COBS 14.3 (best execution), PS22/9
Trust Zone: AMBER

UUID quote_id. 30s TTL (I-23). Spread-adjusted buy_amount.
All amounts Decimal (I-22). UTC timestamps (I-23).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import logging
import uuid

from services.fx_engine.models import (
    FXQuote,
    InMemoryQuoteStore,
    InMemoryRateStore,
    QuoteStatus,
    QuoteStore,
    RateStore,
)
from services.fx_engine.rate_provider import RateProvider
from services.fx_engine.spread_calculator import SpreadCalculator

logger = logging.getLogger(__name__)

QUOTE_TTL = 30  # seconds


class FXQuoter:
    """FX quote generator with 30-second TTL.

    UUID quote_id. Spread applied from SpreadCalculator.
    I-22: all amounts Decimal. I-23: UTC timestamps.
    """

    def __init__(
        self,
        rate_store: RateStore | None = None,
        quote_store: QuoteStore | None = None,
    ) -> None:
        """Initialise quoter with optional stores."""
        self._rate_provider = RateProvider(rate_store or InMemoryRateStore())
        self._spread_calc = SpreadCalculator()
        self._quote_store: QuoteStore = quote_store or InMemoryQuoteStore()

    def create_quote(
        self,
        currency_pair: str,
        sell_amount: Decimal,
        sell_currency: str,
        tenant_id: str = "default",
    ) -> FXQuote | None:
        """Create an FX quote with 30-second TTL.

        I-22: buy_amount = sell_amount * (mid - spread).
        I-23: expires_at = created_at + 30s UTC.

        Args:
            currency_pair: e.g. "GBP/EUR".
            sell_amount: Amount to sell (Decimal, I-22).
            sell_currency: ISO 4217 sell currency.
            tenant_id: Tenant identifier.

        Returns:
            FXQuote or None if rate not found.
        """
        rate = self._rate_provider.get_rate(currency_pair)
        if rate is None:
            logger.warning("No rate found for %s — cannot create quote", currency_pair)
            return None

        spread = self._spread_calc.get_spread(sell_amount)
        buy_amount = self._spread_calc.calculate_buy_amount(sell_amount, rate.mid, spread)

        parts = currency_pair.split("/")
        buy_currency = parts[1] if len(parts) == 2 else currency_pair

        now = datetime.now(UTC)
        quote_id = f"qte_{uuid.uuid4().hex[:8]}"

        quote = FXQuote(
            quote_id=quote_id,
            currency_pair=currency_pair,
            sell_amount=sell_amount,
            sell_currency=sell_currency,
            buy_amount=buy_amount,
            buy_currency=buy_currency,
            rate=rate.mid,
            spread=spread,
            ttl_seconds=QUOTE_TTL,
            status=QuoteStatus.ACTIVE,
            created_at=now.isoformat(),
            expires_at=(now + timedelta(seconds=QUOTE_TTL)).isoformat(),
            tenant_id=tenant_id,
        )
        self._quote_store.save(quote)
        logger.info(
            "Created quote %s %s->%s sell=%s buy=%s spread=%s",
            quote_id,
            sell_currency,
            buy_currency,
            sell_amount,
            buy_amount,
            spread,
        )
        return quote

    def get_quote(self, quote_id: str) -> FXQuote | None:
        """Retrieve an FX quote by ID.

        Args:
            quote_id: Quote identifier.

        Returns:
            FXQuote or None.
        """
        return self._quote_store.get(quote_id)

    def is_quote_valid(self, quote_id: str) -> bool:
        """Check if a quote is still valid (not expired).

        I-23: compares expires_at vs UTC now.

        Args:
            quote_id: Quote identifier.

        Returns:
            True if quote exists, is ACTIVE, and not expired.
        """
        quote = self._quote_store.get(quote_id)
        if quote is None or quote.status != QuoteStatus.ACTIVE:
            return False
        try:
            expires_at = datetime.fromisoformat(quote.expires_at)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            return datetime.now(UTC) < expires_at
        except (ValueError, TypeError):
            return False

    def expire_quote(self, quote_id: str) -> FXQuote:
        """Mark a quote as expired.

        Args:
            quote_id: Quote identifier.

        Returns:
            Updated FXQuote with EXPIRED status.

        Raises:
            ValueError: If quote not found.
        """
        quote = self._quote_store.get(quote_id)
        if quote is None:
            raise ValueError(f"Quote {quote_id} not found")
        updated = quote.model_copy(update={"status": QuoteStatus.EXPIRED})
        self._quote_store.save(updated)
        logger.info("Expired quote %s", quote_id)
        return updated

    def list_active_quotes(self) -> list[FXQuote]:
        """List all currently active FX quotes.

        Returns:
            List of active FXQuote objects.
        """
        return self._quote_store.list_active()

    def get_quote_summary(self) -> dict[str, int]:
        """Get summary of quote counts by status.

        Returns:
            Dict with active, expired, executed, rejected counts.
        """
        all_quotes = self._quote_store.list_active()
        all_statuses: dict[str, int] = {
            "active": 0,
            "expired": 0,
            "executed": 0,
            "rejected": 0,
        }
        for q in all_quotes:
            status_key = q.status.lower()
            if status_key in all_statuses:
                all_statuses[status_key] += 1
        return all_statuses
