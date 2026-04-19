"""
services/fee_management/fee_transparency.py
IL-FME-01 | Phase 41 | banxe-emi-stack

FeeTransparency — public-facing fee disclosure and PS22/9 compliance.
I-01: All monetary values as Decimal — NEVER float.
FCA refs: PS22/9 Consumer Duty §4, BCOBS 5, PS21/3.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from services.fee_management.fee_calculator import FeeCalculator
from services.fee_management.models import (
    FeeRule,
    FeeSchedule,
    InMemoryFeeRuleStore,
    InMemoryFeeScheduleStore,
)


class FeeTransparency:
    """Public fee schedule transparency and PS22/9 disclosure engine."""

    def __init__(
        self,
        rule_store: InMemoryFeeRuleStore | None = None,
        schedule_store: InMemoryFeeScheduleStore | None = None,
        calculator: FeeCalculator | None = None,
    ) -> None:
        self._rules = rule_store or InMemoryFeeRuleStore()
        self._schedules = schedule_store or InMemoryFeeScheduleStore()
        self._calculator = calculator or FeeCalculator(rule_store=self._rules)

    def get_fee_schedule(self) -> list[FeeRule]:
        """Return all active rules (public-facing)."""
        return self._rules.list_rules(active_only=True)

    def compare_plans(self, plan_a: str, plan_b: str) -> dict:
        """Side-by-side comparison of two FeeSchedules."""
        schedule_a = self._schedules.get_schedule(plan_a)
        schedule_b = self._schedules.get_schedule(plan_b)

        def _get_fees(schedule: FeeSchedule | None) -> dict:
            if schedule is None:
                return {}
            fees = {}
            for rule_id in schedule.rules:
                rule = self._rules.get_rule(rule_id)
                if rule:
                    fees[rule.name] = str(
                        rule.amount if rule.percentage is None else rule.percentage
                    )
            return fees

        fees_a = _get_fees(schedule_a)
        fees_b = _get_fees(schedule_b)
        all_keys = set(fees_a) | set(fees_b)
        difference = {
            k: {"plan_a": fees_a.get(k, "N/A"), "plan_b": fees_b.get(k, "N/A")}
            for k in all_keys
            if fees_a.get(k) != fees_b.get(k)
        }
        return {"plan_a": fees_a, "plan_b": fees_b, "difference": difference}

    def estimate_annual_cost(
        self,
        transactions_per_month: int,
        avg_amount: Decimal,
        fx_volume: Decimal,
        tier: str,
    ) -> Decimal:
        """Project 12-month fee total using fee calculator (I-01)."""
        monthly = self._calculator.estimate_monthly_fees(
            account_id="estimate",
            estimated_transactions=transactions_per_month,
            avg_transaction=avg_amount,
            tier=tier,
        )
        fx_rule = None
        for rule in self._rules.list_rules(active_only=True):
            if rule.percentage is not None:
                fx_rule = rule
                break
        annual_fx = Decimal("0")
        if fx_rule and fx_volume > Decimal("0"):
            raw_fx = self._calculator.calculate_fee(fx_rule, fx_volume)
            annual_fx = self._calculator.apply_discount(raw_fx * 12, tier)
        return ((monthly.total_charged * 12) + annual_fx).quantize(Decimal("0.01"))

    def generate_disclosure(self, account_id: str) -> dict:
        """PS22/9 plain-language fee summary for account (FCA Consumer Duty §4)."""
        rules = self.get_fee_schedule()
        key_fees = [
            {"name": r.name, "amount": str(r.amount), "type": r.fee_type.value} for r in rules[:5]
        ]
        monthly_estimate = self._calculator.estimate_monthly_fees(
            account_id=account_id,
            estimated_transactions=10,
            avg_transaction=Decimal("100.00"),
            tier="STANDARD",
        )
        return {
            "summary": (
                "This document summarises the fees that may apply to your Banxe account. "
                "Fees are charged in GBP and deducted from your account balance. "
                "You can request a fee waiver by contacting support. (PS22/9 §4)"
            ),
            "key_fees": key_fees,
            "total_monthly_estimate": monthly_estimate.total_charged,
        }

    def get_regulatory_summary(self) -> dict:
        """Return regulatory metadata for FCA reporting."""
        rules = self._rules.list_rules(active_only=False)
        return {
            "total_rules": len(rules),
            "last_updated": datetime.now(UTC).isoformat(),
            "fca_ref": "PS21/3, BCOBS 5, PS22/9 §4",
        }
