"""
test_wind_down_plan.py — Tests for Wind-Down Plan (SP-THIN GAP-057)
FCA WDPG | banxe-emi-stack
"""

from __future__ import annotations

from decimal import Decimal

from services.resolution.wind_down_plan import (
    TriggerType,
    WindDownFinancials,
    WindDownPlanBuilder,
)


def _fin(
    *,
    liquid: str = "1200000",
    monthly_cost: str = "100000",
    own_funds: str = "500000",
    own_req: str = "400000",
    liquidity_ratio: str = "1.5",
    complaints: str = "0.01",
) -> WindDownFinancials:
    return WindDownFinancials(
        liquid_resources_gbp=Decimal(liquid),
        monthly_wind_down_cost_gbp=Decimal(monthly_cost),
        own_funds_gbp=Decimal(own_funds),
        own_funds_requirement_gbp=Decimal(own_req),
        liquidity_ratio=Decimal(liquidity_ratio),
        open_complaints_rate=Decimal(complaints),
    )


class TestRunway:
    def test_runway_months(self) -> None:
        plan = WindDownPlanBuilder().build(_fin(liquid="1200000", monthly_cost="100000"))
        assert plan.runway_months == Decimal("12.0")

    def test_zero_cost_safe(self) -> None:
        plan = WindDownPlanBuilder().build(_fin(monthly_cost="0"))
        assert plan.runway_months == Decimal("0")


class TestTriggers:
    def test_healthy_no_breach(self) -> None:
        plan = WindDownPlanBuilder().build(_fin())
        assert plan.any_breach is False

    def test_capital_breach(self) -> None:
        plan = WindDownPlanBuilder().build(_fin(own_funds="300000", own_req="400000"))
        cap = next(t for t in plan.triggers if t.trigger_type is TriggerType.CAPITAL)
        assert cap.breached is True
        assert plan.any_breach is True

    def test_liquidity_breach(self) -> None:
        plan = WindDownPlanBuilder().build(_fin(liquidity_ratio="0.8"))
        liq = next(t for t in plan.triggers if t.trigger_type is TriggerType.LIQUIDITY)
        assert liq.breached is True

    def test_conduct_breach(self) -> None:
        plan = WindDownPlanBuilder().build(_fin(complaints="0.20"))
        con = next(t for t in plan.triggers if t.trigger_type is TriggerType.CONDUCT)
        assert con.breached is True


class TestSteps:
    def test_steps_ordered_and_present(self) -> None:
        plan = WindDownPlanBuilder().build(_fin())
        assert len(plan.steps) == 6
        assert "FCA" in plan.steps[0]
        assert plan.fca_guide == "FCA WDPG"
