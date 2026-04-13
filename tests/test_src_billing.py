"""Tests for src/billing/fee_engine.py — GAP-019 D-fee.

Coverage targets: FeeType enum, FeeRule.compute(), FeeRule.applies_to(),
FeeSchedule, FeeEngine.calculate(), tiered brackets, min/max clamping.
"""

from decimal import Decimal

from src.billing import (
    FeeEngine,
    FeeRule,
    FeeSchedule,
    FeeType,
    TransactionContext,
)
from src.billing.fee_engine import TierBracket

# ── FeeRule.applies_to ─────────────────────────────────────────────────────────


class TestFeeRuleAppliesTo:
    def test_all_rails_all_currencies_applies(self):
        rule = FeeRule(FeeType.FLAT, Decimal("1.00"))
        assert rule.applies_to("fps", "GBP") is True

    def test_disabled_rule_never_applies(self):
        rule = FeeRule(FeeType.FLAT, Decimal("1.00"), enabled=False)
        assert rule.applies_to("fps", "GBP") is False

    def test_rail_filter_match(self):
        rule = FeeRule(FeeType.FLAT, Decimal("1.00"), applies_to_rails=["fps", "bacs"])
        assert rule.applies_to("fps", "GBP") is True
        assert rule.applies_to("FPS", "GBP") is True  # case-insensitive

    def test_rail_filter_no_match(self):
        rule = FeeRule(FeeType.FLAT, Decimal("1.00"), applies_to_rails=["fps"])
        assert rule.applies_to("sepa", "GBP") is False

    def test_currency_filter_match(self):
        rule = FeeRule(FeeType.FLAT, Decimal("1.00"), applies_to_currencies=["EUR"])
        assert rule.applies_to("sepa", "EUR") is True
        assert rule.applies_to("sepa", "eur") is True  # case-insensitive

    def test_currency_filter_no_match(self):
        rule = FeeRule(FeeType.FLAT, Decimal("1.00"), applies_to_currencies=["EUR"])
        assert rule.applies_to("fps", "GBP") is False

    def test_rail_and_currency_filter_both_must_match(self):
        rule = FeeRule(
            FeeType.FLAT,
            Decimal("1.00"),
            applies_to_rails=["fps"],
            applies_to_currencies=["GBP"],
        )
        assert rule.applies_to("fps", "GBP") is True
        assert rule.applies_to("fps", "EUR") is False
        assert rule.applies_to("sepa", "GBP") is False


# ── FeeRule.compute ────────────────────────────────────────────────────────────


class TestFeeRuleCompute:
    def test_flat_fee(self):
        rule = FeeRule(FeeType.FLAT, Decimal("0.20"))
        assert rule.compute(Decimal("1000")) == Decimal("0.20")

    def test_flat_fee_zero(self):
        rule = FeeRule(FeeType.FLAT, Decimal("0"))
        assert rule.compute(Decimal("500")) == Decimal("0.00")

    def test_percentage_fee(self):
        rule = FeeRule(FeeType.PERCENTAGE, Decimal("1.5"))
        result = rule.compute(Decimal("1000"))
        assert result == Decimal("15.00")

    def test_percentage_rounds_half_up(self):
        rule = FeeRule(FeeType.PERCENTAGE, Decimal("1"))
        # 1% of 0.005 = 0.00005 → rounds to 0.00
        result = rule.compute(Decimal("0.005"))
        assert result == Decimal("0.00")

    def test_percentage_zero_amount(self):
        rule = FeeRule(FeeType.PERCENTAGE, Decimal("2.5"))
        assert rule.compute(Decimal("0")) == Decimal("0.00")

    def test_monthly_fee(self):
        rule = FeeRule(FeeType.MONTHLY, Decimal("9.99"))
        assert rule.compute(Decimal("0")) == Decimal("9.99")

    def test_minimum_returns_zero(self):
        """MINIMUM type returns 0 from compute(); applied at schedule level."""
        rule = FeeRule(FeeType.MINIMUM, Decimal("0.10"))
        assert rule.compute(Decimal("1000")) == Decimal("0")

    def test_unknown_type_returns_zero(self):
        """Any FeeType not handled explicitly → 0."""
        rule = FeeRule(FeeType.FLAT, Decimal("1.00"))
        # Hack: force an unsupported type via object.__setattr__
        obj = FeeRule.__new__(FeeRule)
        object.__setattr__(obj, "fee_type", "UNKNOWN_FUTURE_TYPE")
        object.__setattr__(obj, "value", Decimal("0"))
        object.__setattr__(obj, "tiers", [])
        object.__setattr__(obj, "description", "")
        object.__setattr__(obj, "applies_to_rails", [])
        object.__setattr__(obj, "applies_to_currencies", [])
        object.__setattr__(obj, "enabled", True)
        result = obj.compute(Decimal("1000"))
        assert result == Decimal("0")


# ── Tiered fees ────────────────────────────────────────────────────────────────


class TestTieredFee:
    """0–£500: 0.5%, £500–£2000: 0.3%, £2000+: 0.1%"""

    def _make_tiered_rule(self) -> FeeRule:
        return FeeRule(
            fee_type=FeeType.TIERED,
            tiers=[
                TierBracket(Decimal("0"), Decimal("500"), Decimal("0.5")),
                TierBracket(Decimal("500"), Decimal("2000"), Decimal("0.3")),
                TierBracket(Decimal("2000"), None, Decimal("0.1")),
            ],
        )

    def test_first_bracket_only(self):
        rule = self._make_tiered_rule()
        # £100: 0.5% = £0.50
        assert rule.compute(Decimal("100")) == Decimal("0.50")

    def test_two_brackets(self):
        rule = self._make_tiered_rule()
        # £1000: 0.5%×£500 + 0.3%×£500 = £2.50 + £1.50 = £4.00
        assert rule.compute(Decimal("1000")) == Decimal("4.00")

    def test_all_three_brackets(self):
        rule = self._make_tiered_rule()
        # £3000: 0.5%×500 + 0.3%×1500 + 0.1%×1000 = 2.50 + 4.50 + 1.00 = 8.00
        assert rule.compute(Decimal("3000")) == Decimal("8.00")

    def test_exact_bracket_boundary(self):
        rule = self._make_tiered_rule()
        # £500: only first bracket (from=0 to=500, amount<=500 check)
        # £500 <= 500 is True, so from_gbp=500 check: 500 <= 500 → skip bracket 2
        # Actually: first bracket from=0, to=500: upper=min(500,500)=500, taxable=500-0=500
        # 0.5%×500 = 2.50
        assert rule.compute(Decimal("500")) == Decimal("2.50")

    def test_empty_tiers(self):
        rule = FeeRule(fee_type=FeeType.TIERED, tiers=[])
        assert rule.compute(Decimal("1000")) == Decimal("0")

    def test_zero_amount(self):
        rule = self._make_tiered_rule()
        assert rule.compute(Decimal("0")) == Decimal("0.00")


# ── FeeSchedule + FeeEngine ────────────────────────────────────────────────────


class TestFeeEngine:
    def _make_fps_schedule(self) -> FeeSchedule:
        return FeeSchedule(
            schedule_id="fps-standard-v1",
            rules=[
                FeeRule(FeeType.FLAT, Decimal("0.20"), description="FPS flat fee"),
                FeeRule(FeeType.PERCENTAGE, Decimal("0"), description="No FX"),
            ],
            version=1,
        )

    def test_basic_flat_fee(self):
        engine = FeeEngine(self._make_fps_schedule())
        txn = TransactionContext(amount_gbp=Decimal("1000"), currency="GBP", rail="fps")
        calc = engine.calculate(txn)
        assert calc.total_fee_gbp == Decimal("0.20")
        assert calc.subtotal_gbp == Decimal("0.20")

    def test_breakdown_contains_all_rules(self):
        engine = FeeEngine(self._make_fps_schedule())
        txn = TransactionContext(amount_gbp=Decimal("500"), currency="GBP", rail="fps")
        calc = engine.calculate(txn)
        assert len(calc.breakdown) == 2

    def test_rail_filtered_rule_excluded(self):
        schedule = FeeSchedule(
            schedule_id="test",
            rules=[
                FeeRule(FeeType.FLAT, Decimal("1.00"), applies_to_rails=["sepa"]),
                FeeRule(
                    FeeType.FLAT, Decimal("0.20"), description="FPS only", applies_to_rails=["fps"]
                ),
            ],
        )
        engine = FeeEngine(schedule)
        txn = TransactionContext(amount_gbp=Decimal("100"), currency="GBP", rail="fps")
        calc = engine.calculate(txn)
        # Only the fps rule should apply
        assert calc.total_fee_gbp == Decimal("0.20")
        assert len(calc.breakdown) == 1

    def test_minimum_fee_floor_applied(self):
        schedule = FeeSchedule(
            schedule_id="test",
            rules=[FeeRule(FeeType.FLAT, Decimal("0"))],
            minimum_fee_gbp=Decimal("0.10"),
        )
        engine = FeeEngine(schedule)
        txn = TransactionContext(amount_gbp=Decimal("0.01"), currency="GBP", rail="fps")
        calc = engine.calculate(txn)
        assert calc.total_fee_gbp == Decimal("0.10")

    def test_maximum_fee_cap_applied(self):
        schedule = FeeSchedule(
            schedule_id="test",
            rules=[FeeRule(FeeType.PERCENTAGE, Decimal("10"))],
            maximum_fee_gbp=Decimal("5.00"),
        )
        engine = FeeEngine(schedule)
        txn = TransactionContext(amount_gbp=Decimal("1000"), currency="GBP", rail="fps")
        calc = engine.calculate(txn)
        # 10% of £1000 = £100, capped at £5
        assert calc.total_fee_gbp == Decimal("5.00")

    def test_multiple_rules_stack(self):
        schedule = FeeSchedule(
            schedule_id="test",
            rules=[
                FeeRule(FeeType.FLAT, Decimal("0.20")),
                FeeRule(FeeType.PERCENTAGE, Decimal("1")),
            ],
        )
        engine = FeeEngine(schedule)
        txn = TransactionContext(amount_gbp=Decimal("100"), currency="GBP", rail="fps")
        calc = engine.calculate(txn)
        # £0.20 + 1%×100 = £0.20 + £1.00 = £1.20
        assert calc.total_fee_gbp == Decimal("1.20")

    def test_zero_fee_engine(self):
        engine = FeeEngine.zero_fee()
        txn = TransactionContext(amount_gbp=Decimal("5000"), currency="GBP", rail="fps")
        calc = engine.calculate(txn)
        assert calc.total_fee_gbp == Decimal("0.00")
        assert calc.is_zero_fee is True

    def test_fee_calculation_attributes(self):
        engine = FeeEngine(self._make_fps_schedule())
        txn = TransactionContext(amount_gbp=Decimal("1000"), currency="GBP", rail="fps")
        calc = engine.calculate(txn)
        assert calc.schedule_id == "fps-standard-v1"
        assert calc.schedule_version == 1
        assert calc.transaction is txn

    def test_effective_rate_pct(self):
        engine = FeeEngine(self._make_fps_schedule())
        txn = TransactionContext(amount_gbp=Decimal("1000"), currency="GBP", rail="fps")
        calc = engine.calculate(txn)
        # 0.20/1000 * 100 = 0.02%
        assert calc.effective_rate_pct() == Decimal("0.0200")

    def test_effective_rate_pct_zero_amount(self):
        engine = FeeEngine.zero_fee()
        txn = TransactionContext(amount_gbp=Decimal("0"), currency="GBP", rail="fps")
        calc = engine.calculate(txn)
        assert calc.effective_rate_pct() == Decimal("0")

    def test_is_zero_fee_false(self):
        engine = FeeEngine(self._make_fps_schedule())
        txn = TransactionContext(amount_gbp=Decimal("100"), currency="GBP", rail="fps")
        calc = engine.calculate(txn)
        assert calc.is_zero_fee is False

    def test_disabled_rule_skipped(self):
        schedule = FeeSchedule(
            schedule_id="test",
            rules=[
                FeeRule(FeeType.FLAT, Decimal("5.00"), enabled=False),
                FeeRule(FeeType.FLAT, Decimal("0.20")),
            ],
        )
        engine = FeeEngine(schedule)
        txn = TransactionContext(amount_gbp=Decimal("100"), currency="GBP", rail="fps")
        calc = engine.calculate(txn)
        assert calc.total_fee_gbp == Decimal("0.20")

    def test_no_rules_returns_minimum(self):
        schedule = FeeSchedule(
            schedule_id="empty",
            rules=[],
            minimum_fee_gbp=Decimal("0"),
        )
        engine = FeeEngine(schedule)
        txn = TransactionContext(amount_gbp=Decimal("100"), currency="GBP", rail="fps")
        calc = engine.calculate(txn)
        assert calc.total_fee_gbp == Decimal("0.00")

    def test_rule_description_fallback(self):
        schedule = FeeSchedule(
            schedule_id="test",
            rules=[FeeRule(FeeType.FLAT, Decimal("1.00"), description="")],
        )
        engine = FeeEngine(schedule)
        txn = TransactionContext(amount_gbp=Decimal("50"), currency="GBP", rail="fps")
        calc = engine.calculate(txn)
        # When description is empty, should use fee_type.value
        assert calc.breakdown[0].rule_description == "FLAT"

    def test_transaction_context_defaults(self):
        txn = TransactionContext(amount_gbp=Decimal("100"))
        assert txn.currency == "GBP"
        assert txn.rail == "fps"
        assert txn.is_fx is False
        assert txn.product_id == ""
