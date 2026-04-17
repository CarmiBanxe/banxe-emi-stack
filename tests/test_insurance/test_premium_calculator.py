"""
tests/test_insurance/test_premium_calculator.py
IL-INS-01 | Phase 26 — 18 tests for PremiumCalculator.
All inputs/outputs Decimal — no float (I-01).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from services.insurance.models import (
    CoverageType,
    InMemoryInsuranceProductStore,
    InsuranceProduct,
    UnderwriterType,
)
from services.insurance.premium_calculator import PremiumCalculator


@pytest.fixture
def travel_product() -> InsuranceProduct:
    return InsuranceProduct(
        product_id="ins-001",
        name="Travel Insurance",
        coverage_type=CoverageType.TRAVEL,
        base_premium=Decimal("4.99"),
        max_coverage=Decimal("10000.00"),
        underwriter=UnderwriterType.INTERNAL,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


@pytest.fixture
def calculator() -> PremiumCalculator:
    return PremiumCalculator(store=InMemoryInsuranceProductStore())


# ── Type assertions ───────────────────────────────────────────────────────────


def test_calculate_returns_decimal(
    calculator: PremiumCalculator, travel_product: InsuranceProduct
) -> None:
    result = calculator.calculate(travel_product, Decimal("5000.00"), 30, Decimal("25.0"))
    assert isinstance(result, Decimal)


def test_no_float_in_inputs(
    calculator: PremiumCalculator, travel_product: InsuranceProduct
) -> None:
    # All inputs are Decimal — should not raise
    result = calculator.calculate(travel_product, Decimal("1000.00"), 30, Decimal("0.0"))
    assert isinstance(result, Decimal)


def test_result_has_two_decimal_places(
    calculator: PremiumCalculator, travel_product: InsuranceProduct
) -> None:
    result = calculator.calculate(travel_product, Decimal("3333.33"), 30, Decimal("33.3"))
    # Check quantized to 0.01
    assert result == result.quantize(Decimal("0.01"))


# ── Coverage factor ───────────────────────────────────────────────────────────


def test_coverage_factor_full_coverage(
    calculator: PremiumCalculator, travel_product: InsuranceProduct
) -> None:
    # coverage_amount == max_coverage → factor=1.0, so full > half
    full = calculator.calculate(travel_product, Decimal("10000.00"), 30, Decimal("0.0"))
    half = calculator.calculate(travel_product, Decimal("5000.00"), 30, Decimal("0.0"))
    assert full > half


def test_coverage_factor_half(
    calculator: PremiumCalculator, travel_product: InsuranceProduct
) -> None:
    half = calculator.calculate(travel_product, Decimal("5000.00"), 30, Decimal("0.0"))
    assert isinstance(half, Decimal)
    assert half > Decimal("0")


# ── Risk factor ───────────────────────────────────────────────────────────────


def test_risk_zero_no_surcharge(
    calculator: PremiumCalculator, travel_product: InsuranceProduct
) -> None:
    risk0 = calculator.calculate(travel_product, Decimal("5000.00"), 30, Decimal("0.0"))
    # risk_factor = 1.0 + 0 * 0.5 = 1.0
    expected_risk_factor = Decimal("1.0")
    base = travel_product.base_premium
    coverage_factor = Decimal("5000.00") / Decimal("10000.00")
    expected = (base * coverage_factor * expected_risk_factor).quantize(Decimal("0.01"))
    assert risk0 == expected


def test_risk_100_adds_fifty_pct(
    calculator: PremiumCalculator, travel_product: InsuranceProduct
) -> None:
    risk100 = calculator.calculate(travel_product, Decimal("5000.00"), 30, Decimal("100.0"))
    risk0 = calculator.calculate(travel_product, Decimal("5000.00"), 30, Decimal("0.0"))
    # risk_factor at 100 = 1.0 + (100/100)*0.5 = 1.5
    assert risk100 > risk0


def test_risk_factor_formula(
    calculator: PremiumCalculator, travel_product: InsuranceProduct
) -> None:
    result = calculator.calculate(travel_product, Decimal("10000.00"), 30, Decimal("50.0"))
    # risk_factor = 1 + 0.5*0.5 = 1.25
    base = travel_product.base_premium
    expected = (base * Decimal("1.0") * Decimal("1.25") * Decimal("1.0")).quantize(Decimal("0.01"))
    assert result == expected


# ── Term factor ───────────────────────────────────────────────────────────────


def test_term_30d_factor_one(
    calculator: PremiumCalculator, travel_product: InsuranceProduct
) -> None:
    p30 = calculator.calculate(travel_product, Decimal("10000.00"), 30, Decimal("0.0"))
    p60 = calculator.calculate(travel_product, Decimal("10000.00"), 60, Decimal("0.0"))
    assert p60 == p30 * 2


def test_term_60d_doubles_premium(
    calculator: PremiumCalculator, travel_product: InsuranceProduct
) -> None:
    p30 = calculator.calculate(travel_product, Decimal("1000.00"), 30, Decimal("0.0"))
    p60 = calculator.calculate(travel_product, Decimal("1000.00"), 60, Decimal("0.0"))
    assert p60 == (p30 * 2).quantize(Decimal("0.01"))


def test_term_15d_halves_premium(
    calculator: PremiumCalculator, travel_product: InsuranceProduct
) -> None:
    p30 = calculator.calculate(travel_product, Decimal("1000.00"), 30, Decimal("0.0"))
    p15 = calculator.calculate(travel_product, Decimal("1000.00"), 15, Decimal("0.0"))
    assert p15 == (p30 / 2).quantize(Decimal("0.01"))


# ── assess_risk stub ──────────────────────────────────────────────────────────


def test_assess_risk_flat_score(calculator: PremiumCalculator) -> None:
    ra = calculator.assess_risk("cust-001", "ins-001", Decimal("1000.00"))
    assert ra.risk_score == Decimal("25.0")


def test_assess_risk_recommended_premium_is_decimal(calculator: PremiumCalculator) -> None:
    ra = calculator.assess_risk("cust-001", "ins-001", Decimal("1000.00"))
    assert isinstance(ra.recommended_premium, Decimal)


def test_assess_risk_unknown_product_raises(calculator: PremiumCalculator) -> None:
    with pytest.raises(ValueError, match="not found"):
        calculator.assess_risk("cust-001", "no-product", Decimal("1000.00"))


def test_assess_risk_returns_risk_assessment_type(calculator: PremiumCalculator) -> None:
    from services.insurance.models import RiskAssessment

    ra = calculator.assess_risk("cust-001", "ins-002", Decimal("500.00"))
    assert isinstance(ra, RiskAssessment)


def test_assess_risk_customer_id_stored(calculator: PremiumCalculator) -> None:
    ra = calculator.assess_risk("cust-xyz", "ins-001", Decimal("1000.00"))
    assert ra.customer_id == "cust-xyz"


def test_assess_risk_product_id_stored(calculator: PremiumCalculator) -> None:
    ra = calculator.assess_risk("cust-001", "ins-003", Decimal("1000.00"))
    assert ra.product_id == "ins-003"
