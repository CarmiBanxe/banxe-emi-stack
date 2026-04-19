"""
tests/test_fee_management/test_fee_transparency.py
IL-FME-01 | Phase 41 | 14 tests
"""

from __future__ import annotations

from decimal import Decimal

from services.fee_management.fee_calculator import FeeCalculator
from services.fee_management.fee_transparency import FeeTransparency
from services.fee_management.models import (
    InMemoryFeeRuleStore,
    InMemoryFeeScheduleStore,
)


def _transparency() -> FeeTransparency:
    rules = InMemoryFeeRuleStore()
    schedules = InMemoryFeeScheduleStore()
    calc = FeeCalculator(rule_store=rules)
    return FeeTransparency(rule_store=rules, schedule_store=schedules, calculator=calc)


class TestGetFeeSchedule:
    def test_returns_list_of_rules(self) -> None:
        rules = _transparency().get_fee_schedule()
        assert isinstance(rules, list)
        assert len(rules) > 0

    def test_all_rules_active(self) -> None:
        rules = _transparency().get_fee_schedule()
        assert all(r.active for r in rules)

    def test_seed_has_5_rules(self) -> None:
        rules = _transparency().get_fee_schedule()
        assert len(rules) == 5


class TestComparePlans:
    def test_compare_returns_dict(self) -> None:
        result = _transparency().compare_plans("plan-a", "plan-b")
        assert "plan_a" in result
        assert "plan_b" in result
        assert "difference" in result

    def test_nonexistent_plans_return_empty(self) -> None:
        result = _transparency().compare_plans("nonexistent-1", "nonexistent-2")
        assert result["plan_a"] == {}
        assert result["plan_b"] == {}


class TestEstimateAnnualCost:
    def test_returns_decimal(self) -> None:
        cost = _transparency().estimate_annual_cost(
            10, Decimal("100.00"), Decimal("0.00"), "STANDARD"
        )
        assert isinstance(cost, Decimal)

    def test_vip_cheaper_than_standard(self) -> None:
        std = _transparency().estimate_annual_cost(
            10, Decimal("100.00"), Decimal("0.00"), "STANDARD"
        )
        vip = _transparency().estimate_annual_cost(10, Decimal("100.00"), Decimal("0.00"), "VIP")
        assert vip <= std

    def test_no_float_in_result(self) -> None:
        cost = _transparency().estimate_annual_cost(
            5, Decimal("200.00"), Decimal("1000.00"), "GOLD"
        )
        assert isinstance(cost, Decimal)
        assert "." in str(cost)

    def test_with_fx_volume_adds_to_cost(self) -> None:
        no_fx = _transparency().estimate_annual_cost(
            10, Decimal("100.00"), Decimal("0"), "STANDARD"
        )
        with_fx = _transparency().estimate_annual_cost(
            10, Decimal("100.00"), Decimal("10000.00"), "STANDARD"
        )
        assert with_fx >= no_fx


class TestGenerateDisclosure:
    def test_disclosure_has_summary(self) -> None:
        result = _transparency().generate_disclosure("acc-1")
        assert "summary" in result
        assert len(result["summary"]) > 20

    def test_disclosure_ps229_reference(self) -> None:
        result = _transparency().generate_disclosure("acc-1")
        assert "PS22/9" in result["summary"]

    def test_disclosure_key_fees_list(self) -> None:
        result = _transparency().generate_disclosure("acc-1")
        assert isinstance(result["key_fees"], list)

    def test_disclosure_monthly_estimate_decimal(self) -> None:
        result = _transparency().generate_disclosure("acc-1")
        assert isinstance(result["total_monthly_estimate"], Decimal)


class TestGetRegulatorySummary:
    def test_returns_fca_ref(self) -> None:
        result = _transparency().get_regulatory_summary()
        assert "fca_ref" in result
        assert "PS21/3" in result["fca_ref"]

    def test_total_rules_positive(self) -> None:
        result = _transparency().get_regulatory_summary()
        assert result["total_rules"] > 0
