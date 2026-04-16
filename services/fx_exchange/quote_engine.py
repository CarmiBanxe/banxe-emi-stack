"""
services/fx_exchange/quote_engine.py
IL-FX-01 | Phase 21

QuoteEngine — generates and validates FX quotes.
bid/ask computed from mid-rate ± spread_bps/2.
Quotes expire after 30 seconds (tight window for FX settlement certainty).
All monetary values are Decimal (I-01).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import uuid

from services.fx_exchange.models import (
    _DEFAULT_SPREADS,
    CurrencyPair,
    FXQuote,
    QuoteStorePort,
    RateSource,
    RateStorePort,
    SpreadConfig,
    get_default_spread_config,
)

_QUOTE_TTL_SECONDS: int = 30
_BPS_DIVISOR: Decimal = Decimal("10000")


class QuoteEngine:
    """Generates live FX quotes with bid/ask spread from SpreadConfig.

    spread_bps comes from SpreadConfig if configured, else falls back to
    default 30 bps (_DEFAULT_SPREAD_BPS from models).
    """

    def __init__(
        self,
        rate_store: RateStorePort,
        quote_store: QuoteStorePort,
        spread_configs: dict[str, SpreadConfig] | None = None,
    ) -> None:
        self._rate_store = rate_store
        self._quote_store = quote_store
        self._spreads: dict[str, SpreadConfig] = spread_configs or dict(_DEFAULT_SPREADS)

    async def get_quote(
        self,
        pair: CurrencyPair,
        amount_base: Decimal,
        entity_id: str,  # noqa: ARG002 — reserved for per-entity spread in future
    ) -> FXQuote:
        """Compute and store a live quote for the given pair and base amount.

        bid = mid_rate * (1 - spread_bps / 2 / 10000)
        ask = mid_rate * (1 + spread_bps / 2 / 10000)
        """
        snapshot = await self._rate_store.get_latest_rate(pair)
        if snapshot is None:
            raise ValueError(f"No rate available for {pair}")

        config = self._spreads.get(str(pair), get_default_spread_config(pair))
        spread_bps = config.base_spread_bps

        half_spread = Decimal(spread_bps) / 2 / _BPS_DIVISOR
        mid = snapshot.rate
        bid = mid * (1 - half_spread)
        ask = mid * (1 + half_spread)

        now = datetime.now(UTC)
        quote = FXQuote(
            quote_id=str(uuid.uuid4()),
            pair=pair,
            rate=mid,
            bid=bid,
            ask=ask,
            spread_bps=spread_bps,
            source=snapshot.source if snapshot.source is not None else RateSource.FALLBACK,
            valid_until=now + timedelta(seconds=_QUOTE_TTL_SECONDS),
            created_at=now,
        )
        await self._quote_store.save_quote(quote)
        return quote

    async def validate_quote(self, quote_id: str) -> bool:
        """Return True iff the quote exists and has not expired."""
        quote = await self._quote_store.get_quote(quote_id)
        if quote is None:
            return False
        return datetime.now(UTC) < quote.valid_until

    async def get_quote_by_id(self, quote_id: str) -> FXQuote | None:
        """Retrieve a quote by its ID (may be expired)."""
        return await self._quote_store.get_quote(quote_id)
