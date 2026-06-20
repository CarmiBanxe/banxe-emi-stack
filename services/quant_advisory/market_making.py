"""
services/quant_advisory/market_making.py — Avellaneda-Stoikov optimal spread
GAP-070 | IMPL-4 | banxe-emi-stack

Avellaneda-Stoikov (2008) reservation price + optimal bid/ask spread.
ADVISORY ONLY — the quotes feed the Dynamic Spread Engine recommendation; this
module NEVER places orders and there is NO autonomous market-making path
(MiCA broker-dealer avoidance, ADR-089/090/091/093).
"""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class ASQuote:
    reservation_price: float
    optimal_spread: float
    bid: float
    ask: float


class AvellanedaStoikov:
    """Analytical A-S optimal market-making quotes (advisory recommendation)."""

    def reservation_price(
        self, mid: float, inventory: float, *, gamma: float, sigma: float, time_left: float
    ) -> float:
        """r = s - q·γ·σ²·(T−t)."""
        return mid - inventory * gamma * sigma * sigma * time_left

    def optimal_spread(self, *, gamma: float, sigma: float, time_left: float, k: float) -> float:
        """δ = γ·σ²·(T−t) + (2/γ)·ln(1 + γ/k)."""
        return gamma * sigma * sigma * time_left + (2.0 / gamma) * math.log(1.0 + gamma / k)

    def quote(
        self,
        mid: float,
        inventory: float,
        *,
        gamma: float,
        sigma: float,
        time_left: float,
        k: float,
    ) -> ASQuote:
        r = self.reservation_price(mid, inventory, gamma=gamma, sigma=sigma, time_left=time_left)
        spread = self.optimal_spread(gamma=gamma, sigma=sigma, time_left=time_left, k=k)
        half = spread / 2.0
        return ASQuote(reservation_price=r, optimal_spread=spread, bid=r - half, ask=r + half)
