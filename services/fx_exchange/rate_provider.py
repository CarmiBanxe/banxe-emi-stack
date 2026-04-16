"""
services/fx_exchange/rate_provider.py
IL-FX-01 | Phase 21

RateProvider — fetches and caches FX rates.
Simulates ECB/Frankfurter rate refresh with realistic Decimal mid-rates.
All rates stored as Decimal (I-01).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from services.fx_exchange.models import (
    _SUPPORTED_PAIRS,
    CurrencyPair,
    RateSnapshot,
    RateSource,
    RateStorePort,
)

# ── Realistic mid-rates (ECB reference, approximate) ──────────────────────────
_SEED_RATES: dict[str, Decimal] = {
    "GBP/EUR": Decimal("1.17"),
    "GBP/USD": Decimal("1.27"),
    "GBP/CHF": Decimal("1.13"),
    "GBP/PLN": Decimal("5.05"),
    "GBP/CZK": Decimal("29.5"),
    "EUR/USD": Decimal("1.08"),
}


class RateProvider:
    """Provides FX mid-rates backed by a RateStorePort.

    In production this would call the Frankfurter self-hosted ECB endpoint.
    In sandbox/test mode it generates deterministic Decimal seed rates.
    """

    def __init__(self, store: RateStorePort) -> None:
        self._store = store

    async def get_rate(self, pair: CurrencyPair) -> RateSnapshot:
        """Return the latest cached rate for a pair.

        Raises:
            ValueError: if the pair is unsupported and no rate is cached.
        """
        snapshot = await self._store.get_latest_rate(pair)
        if snapshot is None:
            pair_key = str(pair)
            if pair_key not in _SEED_RATES:
                raise ValueError(f"Unsupported currency pair: {pair_key}")
            # Auto-seed on first access
            snapshot = RateSnapshot(
                pair=pair,
                rate=_SEED_RATES[pair_key],
                source=RateSource.FALLBACK,
                timestamp=datetime.now(UTC),
            )
            await self._store.save_rate(snapshot)
        return snapshot

    async def get_all_rates(self) -> list[RateSnapshot]:
        """Return the latest rates for all supported pairs."""
        results: list[RateSnapshot] = []
        for pair in _SUPPORTED_PAIRS:
            snapshot = await self._store.get_latest_rate(pair)
            if snapshot is not None:
                results.append(snapshot)
        return results

    async def refresh_rates(self, pairs: list[CurrencyPair]) -> list[RateSnapshot]:
        """Simulate ECB rate refresh — generates realistic Decimal rates.

        In production this calls the Frankfurter API. Here we use seed values
        to keep tests deterministic and free of external deps.
        """
        refreshed: list[RateSnapshot] = []
        now = datetime.now(UTC)
        for pair in pairs:
            key = str(pair)
            rate = _SEED_RATES.get(key, Decimal("1.00"))
            snapshot = RateSnapshot(
                pair=pair,
                rate=rate,
                source=RateSource.ECB,
                timestamp=now,
            )
            await self._store.save_rate(snapshot)
            refreshed.append(snapshot)
        return refreshed

    async def get_rate_history(self, pair: CurrencyPair, limit: int = 50) -> list[RateSnapshot]:
        """Return rate history for a pair (most recent `limit` entries)."""
        return await self._store.get_rate_history(pair, limit)
