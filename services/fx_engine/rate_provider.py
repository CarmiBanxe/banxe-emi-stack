"""
services/fx_engine/rate_provider.py
FX Rate Provider
IL-FXE-01 | Sprint 34 | Phase 48

FCA: FCA COBS 14.3 (best execution), PS22/9
Trust Zone: AMBER

Decimal bid/ask/mid (I-22). Staleness check 60s.
UTC timestamps (I-23). BT-004 live rate stub.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import logging

from services.fx_engine.models import FXRate, InMemoryRateStore, RateStore

logger = logging.getLogger(__name__)

STALE_THRESHOLD_SECONDS = 60


class RateProvider:
    """FX rate provider with staleness detection.

    All amounts Decimal (I-22). UTC timestamps (I-23).
    Logs warning when rate is stale (>60s, I-18).
    """

    def __init__(self, store: RateStore | None = None) -> None:
        """Initialise provider with optional rate store."""
        self._store: RateStore = store or InMemoryRateStore()

    def _is_stale(self, rate: FXRate) -> bool:
        """Check if an FX rate is older than STALE_THRESHOLD_SECONDS."""
        try:
            ts = datetime.fromisoformat(rate.timestamp)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            age = (datetime.now(UTC) - ts).total_seconds()
            return age > STALE_THRESHOLD_SECONDS
        except (ValueError, TypeError):
            return True

    def get_rate(self, currency_pair: str) -> FXRate | None:
        """Get latest FX rate, marking stale if >60s old.

        I-18: logs warning if stale. I-23: UTC comparison.

        Args:
            currency_pair: e.g. "GBP/EUR".

        Returns:
            FXRate or None if not found.
        """
        rate = self._store.get_latest(currency_pair)
        if rate is None:
            return None
        if self._is_stale(rate):
            logger.warning(
                "FX rate is stale for %s (>%ds old)", currency_pair, STALE_THRESHOLD_SECONDS
            )
            updated = rate.model_copy(update={"is_stale": True})
            self._store.save(updated)
            return updated
        return rate

    def get_all_rates(self) -> list[FXRate]:
        """Get all available FX rates.

        Returns:
            List of FXRate objects.
        """
        return self._store.get_all()

    def update_rate(
        self,
        currency_pair: str,
        bid: Decimal,
        ask: Decimal,
        provider: str = "internal",
    ) -> FXRate:
        """Update or create an FX rate.

        I-22: mid = (bid + ask) / 2 as Decimal.
        I-23: timestamp = UTC now.

        Args:
            currency_pair: e.g. "GBP/EUR".
            bid: Bid rate (Decimal, I-22).
            ask: Ask rate (Decimal, I-22).
            provider: Rate provider name.

        Returns:
            Updated FXRate.
        """
        mid = (bid + ask) / Decimal("2")
        parts = currency_pair.split("/")
        base = parts[0] if len(parts) == 2 else currency_pair
        quote = parts[1] if len(parts) == 2 else ""

        existing = self._store.get_latest(currency_pair)
        rate_id = existing.rate_id if existing else f"r_{currency_pair.replace('/', '_').lower()}"

        rate = FXRate(
            rate_id=rate_id,
            currency_pair=currency_pair,
            base_currency=base,
            quote_currency=quote,
            bid=bid,
            ask=ask,
            mid=mid,
            timestamp=datetime.now(UTC).isoformat(),
            provider=provider,
            is_stale=False,
        )
        self._store.save(rate)
        logger.info("Rate updated %s bid=%s ask=%s mid=%s", currency_pair, bid, ask, mid)
        return rate

    def check_staleness(self, currency_pair: str) -> bool:
        """Check if a currency pair's rate is stale.

        Args:
            currency_pair: e.g. "GBP/EUR".

        Returns:
            True if stale or not found.
        """
        rate = self._store.get_latest(currency_pair)
        if rate is None:
            return True
        return self._is_stale(rate)

    def get_bid(self, currency_pair: str) -> Decimal | None:
        """Get bid rate for a currency pair (I-22).

        Args:
            currency_pair: e.g. "GBP/EUR".

        Returns:
            Bid as Decimal or None.
        """
        rate = self.get_rate(currency_pair)
        return rate.bid if rate else None

    def get_ask(self, currency_pair: str) -> Decimal | None:
        """Get ask rate for a currency pair (I-22).

        Args:
            currency_pair: e.g. "GBP/EUR".

        Returns:
            Ask as Decimal or None.
        """
        rate = self.get_rate(currency_pair)
        return rate.ask if rate else None

    def get_mid(self, currency_pair: str) -> Decimal | None:
        """Get mid rate for a currency pair (I-22).

        Args:
            currency_pair: e.g. "GBP/EUR".

        Returns:
            Mid as Decimal or None.
        """
        rate = self.get_rate(currency_pair)
        return rate.mid if rate else None


class LiveRateProvider:
    """Live FX rate provider — BT-004 stub.

    Placeholder for Reuters/Bloomberg integration.
    All methods raise NotImplementedError until BT-004 is implemented.
    """

    def get_rate(self, currency_pair: str) -> FXRate | None:
        """Get live FX rate (BT-004 not yet integrated).

        Raises:
            NotImplementedError: BT-004 live feed not yet available.
        """
        raise NotImplementedError("BT-004: Live FX rate feed not yet integrated")

    def get_all_rates(self) -> list[FXRate]:
        """Get all live rates (BT-004 not yet integrated).

        Raises:
            NotImplementedError: BT-004 live feed not yet available.
        """
        raise NotImplementedError("BT-004: Live FX rate feed not yet integrated")

    def update_rate(
        self, currency_pair: str, bid: Decimal, ask: Decimal, provider: str = "live"
    ) -> FXRate:
        """Update live rate (BT-004 not yet integrated).

        Raises:
            NotImplementedError: BT-004 live feed not yet available.
        """
        raise NotImplementedError("BT-004: Live FX rate feed not yet integrated")

    def check_staleness(self, currency_pair: str) -> bool:
        """Check staleness of live rate (BT-004 not yet integrated).

        Raises:
            NotImplementedError: BT-004 live feed not yet available.
        """
        raise NotImplementedError("BT-004: Live FX rate feed not yet integrated")

    def get_bid(self, currency_pair: str) -> Decimal | None:
        """Get live bid (BT-004 not yet integrated).

        Raises:
            NotImplementedError: BT-004 live feed not yet available.
        """
        raise NotImplementedError("BT-004: Live FX rate feed not yet integrated")

    def get_ask(self, currency_pair: str) -> Decimal | None:
        """Get live ask (BT-004 not yet integrated).

        Raises:
            NotImplementedError: BT-004 live feed not yet available.
        """
        raise NotImplementedError("BT-004: Live FX rate feed not yet integrated")

    def get_mid(self, currency_pair: str) -> Decimal | None:
        """Get live mid (BT-004 not yet integrated).

        Raises:
            NotImplementedError: BT-004 live feed not yet available.
        """
        raise NotImplementedError("BT-004: Live FX rate feed not yet integrated")
