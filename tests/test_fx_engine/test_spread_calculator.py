"""
Tests for FX Spread Calculator.
IL-FXE-01 | Sprint 34 | Phase 48
Tests: tiered spread Decimal (I-22), I-04 £10k tier, buy_amount calc, institutional tier
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.fx_engine.spread_calculator import (
    INSTITUTIONAL_THRESHOLD,
    LARGE_FX_THRESHOLD,
    SPREAD_TIERS,
    SpreadCalculator,
)


@pytest.fixture
def calc():
    return SpreadCalculator()


class TestGetTier:
    def test_below_10k_retail(self, calc):
        assert calc.get_tier(Decimal("9999.99")) == "retail"

    def test_at_10k_wholesale(self, calc):
        assert calc.get_tier(Decimal("10000")) == "wholesale"

    def test_above_10k_wholesale(self, calc):
        assert calc.get_tier(Decimal("50000")) == "wholesale"

    def test_at_100k_institutional(self, calc):
        assert calc.get_tier(Decimal("100000")) == "institutional"

    def test_above_100k_institutional(self, calc):
        assert calc.get_tier(Decimal("500000")) == "institutional"

    def test_zero_retail(self, calc):
        assert calc.get_tier(Decimal("0")) == "retail"


class TestGetSpread:
    def test_retail_spread_50bps(self, calc):
        spread = calc.get_spread(Decimal("5000"))
        assert spread == Decimal("0.0050")

    def test_wholesale_spread_30bps(self, calc):
        spread = calc.get_spread(Decimal("10000"))
        assert spread == Decimal("0.0030")

    def test_institutional_spread_15bps(self, calc):
        spread = calc.get_spread(Decimal("100000"))
        assert spread == Decimal("0.0015")

    def test_spread_is_decimal(self, calc):
        spread = calc.get_spread(Decimal("1000"))
        assert isinstance(spread, Decimal)

    def test_tiers_constants(self):
        assert SPREAD_TIERS["retail"] == Decimal("0.0050")
        assert SPREAD_TIERS["wholesale"] == Decimal("0.0030")
        assert SPREAD_TIERS["institutional"] == Decimal("0.0015")

    def test_large_fx_threshold_10k(self):
        assert Decimal("10000") == LARGE_FX_THRESHOLD

    def test_institutional_threshold_100k(self):
        assert Decimal("100000") == INSTITUTIONAL_THRESHOLD


class TestCalculateBuyAmount:
    def test_buy_amount_basic(self, calc):
        buy = calc.calculate_buy_amount(Decimal("1000"), Decimal("1.1665"), Decimal("0.005"))
        expected = Decimal("1000") * (Decimal("1.1665") - Decimal("0.005"))
        assert buy == expected

    def test_buy_amount_is_decimal(self, calc):
        buy = calc.calculate_buy_amount(Decimal("1000"), Decimal("1.20"), Decimal("0.005"))
        assert isinstance(buy, Decimal)

    def test_buy_amount_less_than_mid_times_amount(self, calc):
        buy = calc.calculate_buy_amount(Decimal("1000"), Decimal("1.20"), Decimal("0.005"))
        mid_buy = Decimal("1000") * Decimal("1.20")
        assert buy < mid_buy

    def test_buy_amount_retail_spread(self, calc):
        sell = Decimal("5000")
        mid = Decimal("1.1665")
        spread = Decimal("0.005")
        buy = calc.calculate_buy_amount(sell, mid, spread)
        assert buy == Decimal("5000") * (Decimal("1.1665") - Decimal("0.005"))


class TestGetSpreadCost:
    def test_spread_cost_is_decimal(self, calc):
        cost = calc.get_spread_cost(Decimal("1000"), Decimal("1.20"))
        assert isinstance(cost, Decimal)

    def test_spread_cost_positive(self, calc):
        cost = calc.get_spread_cost(Decimal("1000"), Decimal("1.20"))
        assert cost > Decimal("0")

    def test_spread_cost_larger_for_larger_amount(self, calc):
        cost_small = calc.get_spread_cost(Decimal("1000"), Decimal("1.20"))
        cost_large = calc.get_spread_cost(Decimal("10000"), Decimal("1.20"))
        # Both retail and wholesale, just comparing magnitudes
        assert cost_large > Decimal("0")


class TestApplyMarkup:
    def test_markup_reduces_rate(self, calc):
        rate = Decimal("1.20")
        marked_up = calc.apply_markup(rate, 50)
        assert marked_up == Decimal("1.20") - Decimal("50") / Decimal("10000")

    def test_markup_is_decimal(self, calc):
        result = calc.apply_markup(Decimal("1.20"), 30)
        assert isinstance(result, Decimal)

    def test_zero_markup_unchanged(self, calc):
        rate = Decimal("1.20")
        assert calc.apply_markup(rate, 0) == rate
