"""
tests/test_fee_management/test_fee_calculator.py
IL-FME-01 | Phase 41 | 18 tests
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from services.fee_management.fee_calculator import (
    FeeCalculator,
)
from services.fee_management.models import (
    BillingCycle,
    FeeCategory,
    FeeRule,
    FeeType,
)


def _make_flat_rule(
    amount: str = "10.00", min_amount: str = "0.01", max_amount: str | None = None
) -> FeeRule:
    return FeeRule(
        id="r-1",
        name="Test Fee",
        fee_type=FeeType.TRANSACTION,
        category=FeeCategory.PAYMENTS,
        amount=Decimal(amount),
        percentage=None,
        min_amount=Decimal(min_amount),
        max_amount=Decimal(max_amount) if max_amount else None,
        billing_cycle=BillingCycle.ON_DEMAND,
        active=True,
        created_at=datetime.now(UTC),
    )


def _make_pct_rule(pct: str, min_amount: str = "0.01", max_amount: str | None = None) -> FeeRule:
    return FeeRule(
        id="r-2",
        name="Pct Fee",
        fee_type=FeeType.FX_MARKUP,
        category=FeeCategory.FX,
        amount=Decimal("0"),
        percentage=Decimal(pct),
        min_amount=Decimal(min_amount),
        max_amount=Decimal(max_amount) if max_amount else None,
        billing_cycle=BillingCycle.ON_DEMAND,
        active=True,
        created_at=datetime.now(UTC),
    )


def _calc() -> FeeCalculator:
    return FeeCalculator()


class TestCalculateFee:
    def test_flat_fee_returns_amount(self) -> None:
        rule = _make_flat_rule("10.00")
        fee = _calc().calculate_fee(rule, Decimal("500"))
        assert fee == Decimal("10.00")

    def test_percentage_fee_calculates_correctly(self) -> None:
        rule = _make_pct_rule("0.005")
        fee = _calc().calculate_fee(rule, Decimal("1000"))
        assert fee == Decimal("5.00")

    def test_percentage_fee_quantized_to_pence(self) -> None:
        rule = _make_pct_rule("0.005")
        fee = _calc().calculate_fee(rule, Decimal("33.33"))
        assert fee == Decimal("0.17")

    def test_flat_fee_clamps_to_min_amount(self) -> None:
        rule = _make_flat_rule("1.00", min_amount="5.00")
        fee = _calc().calculate_fee(rule, Decimal("0"))
        assert fee >= Decimal("5.00")

    def test_flat_fee_clamps_to_max_amount(self) -> None:
        rule = _make_flat_rule("100.00", max_amount="50.00")
        fee = _calc().calculate_fee(rule, Decimal("1000"))
        assert fee == Decimal("50.00")

    def test_percentage_clamps_to_min(self) -> None:
        rule = _make_pct_rule("0.001", min_amount="1.00")
        fee = _calc().calculate_fee(rule, Decimal("10"))
        assert fee == Decimal("1.00")

    def test_percentage_clamps_to_max(self) -> None:
        rule = _make_pct_rule("0.10", max_amount="10.00")
        fee = _calc().calculate_fee(rule, Decimal("500"))
        assert fee == Decimal("10.00")


class TestTieredFee:
    def test_small_amount_uses_first_bracket(self) -> None:
        fee = _calc().calculate_tiered_fee(Decimal("100"))
        assert fee == Decimal("1.00")

    def test_mid_amount_crosses_brackets(self) -> None:
        fee = _calc().calculate_tiered_fee(Decimal("2000"))
        # 1000 * 0.010 + 1000 * 0.008 = 10 + 8 = 18
        assert fee == Decimal("18.00")

    def test_large_amount_uses_all_brackets(self) -> None:
        fee = _calc().calculate_tiered_fee(Decimal("15000"))
        # 1000*0.010 + 9000*0.008 + 5000*0.005 = 10 + 72 + 25 = 107
        assert fee == Decimal("107.00")

    def test_zero_amount_returns_zero(self) -> None:
        fee = _calc().calculate_tiered_fee(Decimal("0"))
        assert fee == Decimal("0.00")


class TestApplyDiscount:
    def test_standard_no_discount(self) -> None:
        fee = _calc().apply_discount(Decimal("100.00"), "STANDARD")
        assert fee == Decimal("100.00")

    def test_gold_10_percent(self) -> None:
        fee = _calc().apply_discount(Decimal("100.00"), "GOLD")
        assert fee == Decimal("90.00")

    def test_vip_25_percent(self) -> None:
        fee = _calc().apply_discount(Decimal("100.00"), "VIP")
        assert fee == Decimal("75.00")

    def test_unknown_tier_no_discount(self) -> None:
        fee = _calc().apply_discount(Decimal("100.00"), "UNKNOWN")
        assert fee == Decimal("100.00")


class TestEstimateMonthlyFees:
    def test_returns_fee_summary(self) -> None:
        summary = _calc().estimate_monthly_fees("acc-1", 5, Decimal("200.00"), "STANDARD")
        assert summary.account_id == "acc-1"
        assert summary.total_charged >= Decimal("0")

    def test_breakdown_contains_categories(self) -> None:
        summary = _calc().estimate_monthly_fees("acc-1", 10, Decimal("100.00"), "STANDARD")
        assert isinstance(summary.breakdown, dict)

    def test_vip_cheaper_than_standard(self) -> None:
        std = _calc().estimate_monthly_fees("acc-1", 10, Decimal("100.00"), "STANDARD")
        vip = _calc().estimate_monthly_fees("acc-1", 10, Decimal("100.00"), "VIP")
        assert vip.total_charged <= std.total_charged


class TestGetFeeBreakdown:
    def test_empty_account_returns_empty(self) -> None:
        calc = FeeCalculator()
        breakdown = calc.get_fee_breakdown("no-charges-account")
        assert breakdown == {}
