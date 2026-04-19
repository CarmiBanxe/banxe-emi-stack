"""
services/fee_management/fee_calculator.py
IL-FME-01 | Phase 41 | banxe-emi-stack

FeeCalculator — fee computation with tier discounts and tiered brackets.
I-01: All monetary values as Decimal — NEVER float.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from services.fee_management.models import (
    BillingCycle,
    FeeRule,
    FeeSummary,
    InMemoryFeeChargeStore,
    InMemoryFeeRuleStore,
)

TIER_DISCOUNTS: dict[str, Decimal] = {
    "STANDARD": Decimal("0"),
    "GOLD": Decimal("0.10"),
    "VIP": Decimal("0.25"),
    "PREMIUM": Decimal("0.15"),
}

TIERED_BRACKETS: list[tuple[Decimal, Decimal | None, Decimal]] = [
    (Decimal("0"), Decimal("1000"), Decimal("0.010")),
    (Decimal("1000"), Decimal("10000"), Decimal("0.008")),
    (Decimal("10000"), None, Decimal("0.005")),
]


class FeeCalculator:
    """Calculates fees using rules, tiered brackets, and tier discounts."""

    def __init__(
        self,
        rule_store: InMemoryFeeRuleStore | None = None,
        charge_store: InMemoryFeeChargeStore | None = None,
    ) -> None:
        self._rules = rule_store or InMemoryFeeRuleStore()
        self._charges = charge_store or InMemoryFeeChargeStore()

    def calculate_fee(self, rule: FeeRule, transaction_amount: Decimal) -> Decimal:
        """Calculate fee for a rule and transaction amount (I-01)."""
        if rule.percentage is not None:
            fee = transaction_amount * rule.percentage
        else:
            fee = rule.amount
        fee = max(fee, rule.min_amount)
        if rule.max_amount is not None:
            fee = min(fee, rule.max_amount)
        return fee.quantize(Decimal("0.01"))

    def calculate_tiered_fee(self, amount: Decimal) -> Decimal:
        """Apply tiered brackets and sum fees for each portion (I-01)."""
        total = Decimal("0")
        remaining = amount
        prev_threshold = Decimal("0")
        for lower, upper, rate in TIERED_BRACKETS:
            if remaining <= Decimal("0"):
                break
            if upper is None:
                portion = remaining
            else:
                bracket_size = upper - lower
                portion = min(remaining, bracket_size)
            total += portion * rate
            remaining -= portion
            if upper is not None:
                prev_threshold = upper
        _ = prev_threshold
        return total.quantize(Decimal("0.01"))

    def apply_discount(self, fee: Decimal, tier: str) -> Decimal:
        """Apply tier discount to a fee (I-01)."""
        discount = TIER_DISCOUNTS.get(tier, Decimal("0"))
        return (fee * (1 - discount)).quantize(Decimal("0.01"))

    def estimate_monthly_fees(
        self,
        account_id: str,
        estimated_transactions: int,
        avg_transaction: Decimal,
        tier: str,
    ) -> FeeSummary:
        """Project maintenance + transaction fees for a month (I-01)."""
        now = datetime.now(UTC)
        maintenance_rule = None
        transaction_rule = None
        for rule in self._rules.list_rules(active_only=True):
            if rule.billing_cycle == BillingCycle.MONTHLY and maintenance_rule is None:
                maintenance_rule = rule
            if rule.billing_cycle == BillingCycle.ON_DEMAND and transaction_rule is None:
                transaction_rule = rule
        total_maintenance = Decimal("0")
        if maintenance_rule:
            total_maintenance = self.apply_discount(
                self.calculate_fee(maintenance_rule, Decimal("0")), tier
            )
        total_transactions = Decimal("0")
        if transaction_rule and estimated_transactions > 0:
            per_tx = self.apply_discount(
                self.calculate_fee(transaction_rule, avg_transaction), tier
            )
            total_transactions = (per_tx * estimated_transactions).quantize(Decimal("0.01"))
        total_charged = (total_maintenance + total_transactions).quantize(Decimal("0.01"))
        breakdown: dict[str, Decimal] = {}
        if maintenance_rule:
            breakdown[maintenance_rule.category.value] = total_maintenance
        if transaction_rule and estimated_transactions > 0:
            cat_key = transaction_rule.category.value
            breakdown[cat_key] = (
                breakdown.get(cat_key, Decimal("0")) + total_transactions
            ).quantize(Decimal("0.01"))
        return FeeSummary(
            account_id=account_id,
            period_start=now,
            period_end=now,
            total_charged=total_charged,
            total_waived=Decimal("0"),
            total_paid=Decimal("0"),
            outstanding=total_charged,
            breakdown=breakdown,
        )

    def get_fee_breakdown(self, account_id: str) -> dict[str, Decimal]:
        """Sum charges by FeeCategory for an account (I-01)."""
        charges = self._charges.list_charges(account_id)
        breakdown: dict[str, Decimal] = {}
        for charge in charges:
            rule = self._rules.get_rule(charge.rule_id)
            if rule is None:
                key = "OTHER"
            else:
                key = rule.category.value
            breakdown[key] = (breakdown.get(key, Decimal("0")) + charge.amount).quantize(
                Decimal("0.01")
            )
        return breakdown
