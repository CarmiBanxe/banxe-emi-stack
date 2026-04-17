"""
tests/test_savings/test_interest_calculator.py — Unit tests for InterestCalculator
IL-SIE-01 | Phase 31 | banxe-emi-stack
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.savings.interest_calculator import InterestCalculator


@pytest.fixture()
def calc() -> InterestCalculator:
    return InterestCalculator()


# ── calculate_daily_interest ───────────────────────────────────────────────────


def test_daily_interest_basic(calc: InterestCalculator) -> None:
    # £10000 @ 5% / 365 = 1.36986... ≈ 1.36986301
    result = calc.calculate_daily_interest(Decimal("10000"), Decimal("0.05"))
    assert result == Decimal("1.36986301")


def test_daily_interest_zero_balance(calc: InterestCalculator) -> None:
    assert calc.calculate_daily_interest(Decimal("0"), Decimal("0.05")) == Decimal("0")


def test_daily_interest_zero_rate(calc: InterestCalculator) -> None:
    assert calc.calculate_daily_interest(Decimal("10000"), Decimal("0")) == Decimal("0")


def test_daily_interest_is_decimal(calc: InterestCalculator) -> None:
    result = calc.calculate_daily_interest(Decimal("5000"), Decimal("0.043"))
    assert isinstance(result, Decimal)


def test_daily_interest_8dp_precision(calc: InterestCalculator) -> None:
    result = calc.calculate_daily_interest(Decimal("1000"), Decimal("0.043"))
    # Verify exactly 8dp
    assert result == result.quantize(Decimal("0.00000001"))


def test_daily_interest_negative_balance_returns_zero(calc: InterestCalculator) -> None:
    assert calc.calculate_daily_interest(Decimal("-100"), Decimal("0.05")) == Decimal("0")


# ── calculate_aer_from_gross ───────────────────────────────────────────────────


def test_aer_higher_than_gross_for_daily_compound(calc: InterestCalculator) -> None:
    gross = Decimal("0.043")
    aer = calc.calculate_aer_from_gross(gross, compounds_per_year=365)
    assert aer > gross


def test_aer_returns_decimal(calc: InterestCalculator) -> None:
    result = calc.calculate_aer_from_gross(Decimal("0.05"))
    assert isinstance(result, Decimal)


def test_aer_annual_compound_equals_gross(calc: InterestCalculator) -> None:
    gross = Decimal("0.05")
    aer = calc.calculate_aer_from_gross(gross, compounds_per_year=1)
    # For n=1: AER = (1 + r/1)^1 - 1 = r
    assert aer == gross


# ── calculate_maturity_amount ──────────────────────────────────────────────────


def test_maturity_amount_365_days(calc: InterestCalculator) -> None:
    # £1000 @ 5% for 365 days = £1050.00
    result = calc.calculate_maturity_amount(Decimal("1000"), Decimal("0.05"), 365)
    assert result == Decimal("1000") + Decimal("1000") * Decimal("0.05")


def test_maturity_amount_greater_than_principal(calc: InterestCalculator) -> None:
    result = calc.calculate_maturity_amount(Decimal("5000"), Decimal("0.051"), 365)
    assert result > Decimal("5000")


def test_maturity_amount_is_decimal(calc: InterestCalculator) -> None:
    result = calc.calculate_maturity_amount(Decimal("1000"), Decimal("0.05"), 91)
    assert isinstance(result, Decimal)


# ── apply_tax_withholding ──────────────────────────────────────────────────────


def test_tax_withholding_20pct(calc: InterestCalculator) -> None:
    result = calc.apply_tax_withholding(Decimal("100.00"))
    assert result["gross_interest"] == "100.00"
    assert result["tax_withheld"] == "20.00"
    assert result["net_interest"] == "80.00"


def test_tax_withholding_zero_rate(calc: InterestCalculator) -> None:
    result = calc.apply_tax_withholding(Decimal("100.00"), Decimal("0"))
    assert result["tax_withheld"] == "0.00"
    assert result["net_interest"] == "100.00"


def test_tax_withholding_returns_strings(calc: InterestCalculator) -> None:
    result = calc.apply_tax_withholding(Decimal("50.00"))
    assert isinstance(result["gross_interest"], str)
    assert isinstance(result["tax_withheld"], str)


def test_tax_withholding_zero_interest(calc: InterestCalculator) -> None:
    result = calc.apply_tax_withholding(Decimal("0"))
    assert result["tax_withheld"] == "0.00"
    assert result["net_interest"] == "0.00"


# ── calculate_penalty_amount ───────────────────────────────────────────────────


def test_penalty_fixed_12m_90_days(calc: InterestCalculator) -> None:
    # £10000 @ 5.1% for 90 days
    result = calc.calculate_penalty_amount(Decimal("10000"), Decimal("0.051"), 90)
    assert isinstance(result, Decimal)
    assert result > Decimal("0")


def test_penalty_zero_balance(calc: InterestCalculator) -> None:
    assert calc.calculate_penalty_amount(Decimal("0"), Decimal("0.051"), 90) == Decimal("0.00")


def test_penalty_zero_days(calc: InterestCalculator) -> None:
    assert calc.calculate_penalty_amount(Decimal("10000"), Decimal("0.051"), 0) == Decimal("0.00")


def test_penalty_is_2dp(calc: InterestCalculator) -> None:
    result = calc.calculate_penalty_amount(Decimal("10000"), Decimal("0.051"), 90)
    assert result == result.quantize(Decimal("0.01"))
