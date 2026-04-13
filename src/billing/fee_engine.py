"""Fee Engine — GAP-019 D-fee.

Calculates transaction fees from a configurable FeeSchedule.

Fee types:
  FLAT        — fixed GBP amount per transaction (e.g. £0.20 per FPS)
  PERCENTAGE  — % of transaction amount (e.g. 1.5% FX fee)
  TIERED      — different rates per volume bracket (e.g. 0-£500: 0.5%, 500+: 0.3%)
  MONTHLY     — subscription/account fee (one per billing period, not per txn)
  MINIMUM     — floor fee: max(calculated, minimum) — e.g. min £0.10

Multiple rules stack: total_fee = sum(rule.calculate(txn) for rule in schedule.rules).
Rules can be marked optional_if_zero=True to skip zero contributions.

FCA / Consumer Duty:
  PS22/9 §2: Products must demonstrate fair value.
  All amounts Decimal (I-24). Schedule changes require CFO approval.
  FeeEngine.calculate() always returns FeeCalculation with full audit breakdown.

Usage:
    schedule = FeeSchedule(
        schedule_id="fps-standard-v1",
        rules=[
            FeeRule(FeeType.FLAT, Decimal("0.20"), description="FPS flat fee"),
            FeeRule(FeeType.PERCENTAGE, Decimal("0"), description="No FX markup"),
        ],
    )
    engine = FeeEngine(schedule)
    calc = engine.calculate(TransactionContext(
        amount_gbp=Decimal("1000"),
        currency="GBP",
        rail="fps",
        product_id="emoney-account-v1",
    ))
    print(calc.total_fee_gbp)   # Decimal("0.20")
    print(calc.breakdown)       # list of rule contributions
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
import logging

logger = logging.getLogger(__name__)

# Rounding: halfeven is standard, but fees round up (ROUND_HALF_UP) per FCA guidance
_FEE_ROUNDING = ROUND_HALF_UP
_PENNY = Decimal("0.01")


class FeeType(str, Enum):
    FLAT = "FLAT"  # Fixed GBP per transaction
    PERCENTAGE = "PERCENTAGE"  # % of transaction amount
    TIERED = "TIERED"  # Tiered rate by amount bracket
    MONTHLY = "MONTHLY"  # Subscription (not per-transaction)
    MINIMUM = "MINIMUM"  # Floor: max(computed, minimum_gbp)


@dataclass(frozen=True)
class TierBracket:
    """One bracket in a tiered fee schedule.

    Attributes:
        from_gbp: Lower bound (inclusive). Use Decimal("0") for the first bracket.
        to_gbp:   Upper bound (exclusive). Use None for the last (open-ended) bracket.
        rate:     Fee rate (percentage expressed as Decimal, e.g. Decimal("0.5") = 0.5%).
    """

    from_gbp: Decimal
    to_gbp: Decimal | None  # None = unbounded upper
    rate_pct: Decimal  # e.g. Decimal("0.5") → 0.5%


@dataclass
class FeeRule:
    """One fee component within a FeeSchedule.

    Attributes:
        fee_type:         Type of fee calculation.
        value:            For FLAT: amount in GBP. For PERCENTAGE: rate (e.g. 1.5 = 1.5%).
                          For MINIMUM: minimum floor in GBP. For TIERED: ignored (use tiers).
        tiers:            For TIERED fee_type only.
        description:      Human-readable label for audit/invoice.
        applies_to_rails: If set, rule only applies to listed rails (e.g. ["fps", "sepa"]).
                          Empty list = all rails.
        applies_to_currencies: If set, rule only applies to listed ISO-4217 codes.
        enabled:          Set False to temporarily disable a rule without deleting it.
    """

    fee_type: FeeType
    value: Decimal = Decimal("0")
    tiers: list[TierBracket] = field(default_factory=list)
    description: str = ""
    applies_to_rails: list[str] = field(default_factory=list)
    applies_to_currencies: list[str] = field(default_factory=list)
    enabled: bool = True

    def applies_to(self, rail: str, currency: str) -> bool:
        """Return True if this rule applies to the given rail/currency."""
        if not self.enabled:
            return False
        rail_ok = not self.applies_to_rails or rail.lower() in [
            r.lower() for r in self.applies_to_rails
        ]
        curr_ok = not self.applies_to_currencies or currency.upper() in [
            c.upper() for c in self.applies_to_currencies
        ]
        return rail_ok and curr_ok

    def compute(self, amount_gbp: Decimal) -> Decimal:
        """Compute this rule's fee contribution for amount_gbp.

        Returns Decimal rounded to penny precision.
        """
        if self.fee_type == FeeType.FLAT:
            return self.value.quantize(_PENNY, rounding=_FEE_ROUNDING)

        if self.fee_type == FeeType.PERCENTAGE:
            raw = amount_gbp * self.value / Decimal("100")
            return raw.quantize(_PENNY, rounding=_FEE_ROUNDING)

        if self.fee_type == FeeType.TIERED:
            return self._compute_tiered(amount_gbp)

        if self.fee_type == FeeType.MONTHLY:
            return self.value.quantize(_PENNY, rounding=_FEE_ROUNDING)

        if self.fee_type == FeeType.MINIMUM:
            return Decimal("0")  # MINIMUM is applied at schedule level, not here

        return Decimal("0")

    def _compute_tiered(self, amount_gbp: Decimal) -> Decimal:
        """Apply tiered rate: sum across brackets that amount_gbp spans."""
        if not self.tiers:
            return Decimal("0")

        total = Decimal("0")
        for bracket in self.tiers:
            if amount_gbp <= bracket.from_gbp:
                continue
            upper = bracket.to_gbp if bracket.to_gbp is not None else amount_gbp
            taxable = min(amount_gbp, upper) - bracket.from_gbp
            if taxable <= Decimal("0"):
                continue
            total += taxable * bracket.rate_pct / Decimal("100")

        return total.quantize(_PENNY, rounding=_FEE_ROUNDING)


@dataclass
class FeeSchedule:
    """Named collection of FeeRule objects for one product/rail combination.

    Attributes:
        schedule_id: Unique identifier (used in audit trail).
        rules:       Ordered list of fee rules to apply.
        minimum_fee_gbp: Global floor applied after summing all rules.
        maximum_fee_gbp: Global cap (None = no cap).
        description: Human-readable name.
        version:     Incremented on each schedule amendment (CFO approval required).
    """

    schedule_id: str
    rules: list[FeeRule] = field(default_factory=list)
    minimum_fee_gbp: Decimal = Decimal("0")
    maximum_fee_gbp: Decimal | None = None
    description: str = ""
    version: int = 1


@dataclass(frozen=True)
class TransactionContext:
    """Input to FeeEngine.calculate().

    Attributes:
        amount_gbp:  Transaction amount in GBP (Decimal, never float — I-24).
        currency:    ISO-4217 transaction currency.
        rail:        Payment rail: "fps" | "sepa" | "chaps" | "bacs" | "card".
        product_id:  EMI product ID (for product-specific rule filtering).
        is_fx:       True if currency != "GBP" (triggers FX markup rules).
    """

    amount_gbp: Decimal
    currency: str = "GBP"
    rail: str = "fps"
    product_id: str = ""
    is_fx: bool = False


@dataclass
class RuleContribution:
    """One rule's contribution to the total fee (for audit breakdown)."""

    rule_description: str
    fee_type: FeeType
    computed_gbp: Decimal


@dataclass
class FeeCalculation:
    """Complete fee calculation result with audit breakdown.

    Attributes:
        transaction: The input context.
        breakdown:   Per-rule contribution list.
        subtotal_gbp: Sum before minimum/maximum clamping.
        total_fee_gbp: Final fee (after min/max clamping).
        schedule_id: Which schedule was used.
        schedule_version: Schedule version at time of calculation.
        is_zero_fee: True if total_fee_gbp == 0 (e.g. internal transfer).
    """

    transaction: TransactionContext
    breakdown: list[RuleContribution]
    subtotal_gbp: Decimal
    total_fee_gbp: Decimal
    schedule_id: str
    schedule_version: int

    @property
    def is_zero_fee(self) -> bool:
        return self.total_fee_gbp == Decimal("0")

    def effective_rate_pct(self) -> Decimal:
        """Fee as percentage of transaction amount (0 if amount is 0)."""
        if self.transaction.amount_gbp == Decimal("0"):
            return Decimal("0")
        return (self.total_fee_gbp / self.transaction.amount_gbp * Decimal("100")).quantize(
            Decimal("0.0001"), rounding=_FEE_ROUNDING
        )


class FeeEngine:
    """Calculate fees from a FeeSchedule for a given TransactionContext.

    The engine is stateless — instantiate once, call calculate() many times.

    Args:
        schedule: The fee schedule to apply.
    """

    def __init__(self, schedule: FeeSchedule) -> None:
        self._schedule = schedule

    def calculate(self, txn: TransactionContext) -> FeeCalculation:
        """Calculate the total fee for txn against the schedule.

        Steps:
          1. For each enabled rule that applies to txn.rail + txn.currency: compute contribution.
          2. Sum contributions → subtotal.
          3. Clamp to schedule.minimum_fee_gbp (floor) and maximum_fee_gbp (cap).
          4. Return FeeCalculation with full breakdown.
        """
        breakdown: list[RuleContribution] = []
        subtotal = Decimal("0")

        for rule in self._schedule.rules:
            if not rule.applies_to(txn.rail, txn.currency):
                logger.debug(
                    "FeeEngine: skipping rule '%s' (rail/currency mismatch)", rule.description
                )
                continue

            contribution = rule.compute(txn.amount_gbp)
            breakdown.append(
                RuleContribution(
                    rule_description=rule.description or rule.fee_type.value,
                    fee_type=rule.fee_type,
                    computed_gbp=contribution,
                )
            )
            subtotal += contribution

        # Apply minimum floor
        total = max(subtotal, self._schedule.minimum_fee_gbp)

        # Apply maximum cap
        if self._schedule.maximum_fee_gbp is not None:
            total = min(total, self._schedule.maximum_fee_gbp)

        total = total.quantize(_PENNY, rounding=_FEE_ROUNDING)

        logger.debug(
            "FeeEngine [%s v%d]: txn=£%s rail=%s → fee=£%s (subtotal=£%s)",
            self._schedule.schedule_id,
            self._schedule.version,
            txn.amount_gbp,
            txn.rail,
            total,
            subtotal,
        )

        return FeeCalculation(
            transaction=txn,
            breakdown=breakdown,
            subtotal_gbp=subtotal.quantize(_PENNY, rounding=_FEE_ROUNDING),
            total_fee_gbp=total,
            schedule_id=self._schedule.schedule_id,
            schedule_version=self._schedule.version,
        )

    @classmethod
    def zero_fee(cls) -> FeeEngine:
        """Return an engine with no fees (for internal / test transactions)."""
        return cls(FeeSchedule(schedule_id="zero-fee", description="No fee schedule"))
