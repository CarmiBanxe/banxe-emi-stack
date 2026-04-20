"""
services/fx_engine/spread_calculator.py
FX Spread Calculator
IL-FXE-01 | Sprint 34 | Phase 48

FCA: FCA COBS 14.3 (best execution), PS22/9
Trust Zone: AMBER

Tiered spread by volume (I-04 £10k tier).
All amounts Decimal (I-22). Never float.
"""

from __future__ import annotations

from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

# Tiered spread by volume (I-04: £10k tier)
SPREAD_TIERS: dict[str, Decimal] = {
    "retail": Decimal("0.0050"),  # < £10k: 50 bps
    "wholesale": Decimal("0.0030"),  # ≥ £10k, < £100k: 30 bps
    "institutional": Decimal("0.0015"),  # ≥ £100k: 15 bps
}
LARGE_FX_THRESHOLD = Decimal("10000")  # I-04
INSTITUTIONAL_THRESHOLD = Decimal("100000")


class SpreadCalculator:
    """Tiered FX spread calculator.

    Spread tiers based on sell_amount (I-04 £10k threshold).
    All calculations in Decimal (I-22). Never float.
    """

    def get_tier(self, sell_amount: Decimal) -> str:
        """Get spread tier for a sell amount.

        I-04: £10k and £100k thresholds.

        Args:
            sell_amount: Amount to sell (Decimal, I-22).

        Returns:
            Tier name: 'retail', 'wholesale', or 'institutional'.
        """
        if sell_amount >= INSTITUTIONAL_THRESHOLD:
            return "institutional"
        if sell_amount >= LARGE_FX_THRESHOLD:
            return "wholesale"
        return "retail"

    def get_spread(self, sell_amount: Decimal) -> Decimal:
        """Get spread rate for a sell amount (I-22).

        I-04: < £10k → retail 50bps, ≥ £10k → wholesale 30bps,
              ≥ £100k → institutional 15bps.

        Args:
            sell_amount: Amount to sell (Decimal, I-22).

        Returns:
            Spread as Decimal fraction.
        """
        tier = self.get_tier(sell_amount)
        spread = SPREAD_TIERS[tier]
        logger.info("Spread %s for amount=%s tier=%s", spread, sell_amount, tier)
        return spread

    def calculate_buy_amount(
        self, sell_amount: Decimal, mid_rate: Decimal, spread: Decimal
    ) -> Decimal:
        """Calculate buy amount after applying spread.

        effective_rate = mid_rate - spread
        buy_amount = sell_amount * effective_rate

        Args:
            sell_amount: Amount to sell (Decimal, I-22).
            mid_rate: Mid-market rate (Decimal, I-22).
            spread: Spread rate (Decimal, I-22).

        Returns:
            Buy amount as Decimal (I-22).
        """
        effective_rate = mid_rate - spread
        buy_amount = sell_amount * effective_rate
        return buy_amount

    def get_spread_cost(self, sell_amount: Decimal, mid_rate: Decimal) -> Decimal:
        """Calculate spread cost in base currency terms.

        Args:
            sell_amount: Amount to sell (Decimal, I-22).
            mid_rate: Mid-market rate (Decimal, I-22).

        Returns:
            Spread cost as Decimal (I-22).
        """
        spread = self.get_spread(sell_amount)
        buy_at_mid = sell_amount * mid_rate
        buy_at_effective = self.calculate_buy_amount(sell_amount, mid_rate, spread)
        return buy_at_mid - buy_at_effective

    def apply_markup(self, rate: Decimal, markup_bps: int) -> Decimal:
        """Apply markup in basis points to a rate.

        Args:
            rate: Base rate (Decimal, I-22).
            markup_bps: Markup in basis points (integer).

        Returns:
            Rate with markup applied as Decimal (I-22).
        """
        markup = Decimal(markup_bps) / Decimal("10000")
        return rate - markup
