"""
services/multi_currency/currency_router.py — Stateless FX routing logic.

Phase 22 | IL-MCL-01 | banxe-emi-stack

Provides path-finding (direct or via intermediate currency), route cost
calculation, and strategy-based routing recommendations.

Note: Risk/analytical scores (spread_bps) are int — monetary amounts remain Decimal.
"""

from __future__ import annotations

from services.multi_currency.models import RoutingStrategy

# Intermediate currencies tried in order when no direct pair exists.
_HUB_CURRENCIES: list[str] = ["GBP", "EUR", "USD"]


class CurrencyRouter:
    """Stateless routing logic — no external dependencies."""

    async def find_cheapest_path(
        self,
        from_currency: str,
        to_currency: str,
        available_pairs: list[str],
    ) -> list[str]:
        """Return an ordered list of currency codes representing the conversion path.

        Direct pair (e.g. "GBP/EUR") → [from_currency, to_currency].
        Single-hop via hub (e.g. GBP→USD→PLN) → [from, hub, to].
        No path found → raises ValueError.

        Args:
            available_pairs: list of "BASE/QUOTE" strings, e.g. ["GBP/EUR", "EUR/USD"].

        Raises:
            ValueError: if no routing path can be found.
        """
        if from_currency == to_currency:
            return [from_currency]

        pair_set = set(available_pairs)

        # Direct pair check (both directions)
        if f"{from_currency}/{to_currency}" in pair_set:
            return [from_currency, to_currency]
        if f"{to_currency}/{from_currency}" in pair_set:
            return [from_currency, to_currency]

        # Single-hop via hub currencies
        for hub in _HUB_CURRENCIES:
            if hub in (from_currency, to_currency):
                continue
            can_reach_hub = (
                f"{from_currency}/{hub}" in pair_set or f"{hub}/{from_currency}" in pair_set
            )
            can_reach_dest = (
                f"{hub}/{to_currency}" in pair_set or f"{to_currency}/{hub}" in pair_set
            )
            if can_reach_hub and can_reach_dest:
                return [from_currency, hub, to_currency]

        raise ValueError(f"No routing path found: {from_currency} → {to_currency}")

    async def get_route_cost(
        self,
        path: list[str],
        spreads: dict[str, int],
    ) -> int:
        """Return total spread_bps for the given path.

        Args:
            path: ordered list of currency codes, e.g. ["GBP", "EUR", "USD"].
            spreads: mapping "BASE/QUOTE" → spread_bps (int).

        Returns:
            Sum of spread_bps for each hop in the path.
        """
        total = 0
        for i in range(len(path) - 1):
            base = path[i]
            quote = path[i + 1]
            key = f"{base}/{quote}"
            rev_key = f"{quote}/{base}"
            if key in spreads:
                total += spreads[key]
            elif rev_key in spreads:
                total += spreads[rev_key]
        return total

    async def recommend_route(
        self,
        from_currency: str,
        to_currency: str,
        strategy: RoutingStrategy,
    ) -> dict:
        """Return a routing recommendation dict for the given strategy.

        Returns:
            {"path": [...], "estimated_spread_bps": int, "strategy": strategy.value}
        """
        # Default available pairs for all supported currencies
        default_pairs = [
            "GBP/EUR",
            "GBP/USD",
            "GBP/CHF",
            "GBP/PLN",
            "GBP/CZK",
            "GBP/SEK",
            "GBP/NOK",
            "GBP/DKK",
            "GBP/HUF",
            "EUR/USD",
            "EUR/CHF",
            "EUR/PLN",
            "EUR/CZK",
            "EUR/SEK",
            "EUR/NOK",
            "EUR/DKK",
            "EUR/HUF",
            "USD/CHF",
        ]
        # Default spreads (bps) by strategy
        if strategy == RoutingStrategy.CHEAPEST:
            spreads = {pair: 10 for pair in default_pairs}
        elif strategy == RoutingStrategy.FASTEST:
            spreads = {pair: 25 for pair in default_pairs}
        else:  # DIRECT
            spreads = {pair: 15 for pair in default_pairs}

        try:
            path = await self.find_cheapest_path(from_currency, to_currency, default_pairs)
        except ValueError:
            path = [from_currency, to_currency]

        cost = await self.get_route_cost(path, spreads)
        return {
            "path": path,
            "estimated_spread_bps": cost,
            "strategy": strategy.value,
        }
