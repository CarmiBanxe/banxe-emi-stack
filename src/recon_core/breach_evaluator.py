"""Generic, regime-parameterised breach evaluator.

The single breach-decision primitive shared by both safeguarding regimes. It is
constructed with a ``threshold`` and a ``breach_kind`` LABEL — both injected by
the caller — and answers one question: does a reconciliation magnitude exceed the
threshold?

    decision = BreachEvaluator(threshold, breach_kind).evaluate(amount)

Regime wiring (thresholds are INPUTS, never unified — see S6.2 / ADR-SAF-01):
    * CASS 15   → BreachEvaluator(Decimal("0.01"), "BREAK")  — aggregate penny-exact
    * CASS 7.15 → BreachEvaluator(Decimal("100"),  "HITL")   — line-item HITL escalation

Boundary semantics (shared, MANDATORY for equivalence):
    breach  ⟺  amount  >  threshold     (strict — equal-to-threshold is NOT a breach)
    clear   ⟺  amount  <= threshold

``amount`` is expected to be a non-negative magnitude (an absolute difference or a
net discrepancy). Invariant I-01: Decimal only.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class BreachDecision:
    """Immutable outcome of a single breach evaluation."""

    is_breach: bool
    breach_kind: str | None  # the injected regime label, or None when within threshold
    amount: Decimal
    threshold: Decimal


class BreachEvaluator:
    """Threshold-parameterised breach gate. Regime-agnostic and stateless."""

    def __init__(self, threshold: Decimal, breach_kind: str) -> None:
        if not isinstance(threshold, Decimal):
            raise TypeError(f"threshold must be Decimal, got {type(threshold).__name__} (I-01)")
        if not breach_kind:
            raise ValueError("breach_kind must be a non-empty regime label")
        self._threshold = threshold
        self._breach_kind = breach_kind

    @property
    def threshold(self) -> Decimal:
        return self._threshold

    @property
    def breach_kind(self) -> str:
        return self._breach_kind

    def evaluate(self, amount: Decimal) -> BreachDecision:
        """Return a BreachDecision for ``amount`` against the injected threshold.

        Breach iff ``amount > threshold`` (strict). At or below threshold clears.
        """
        if not isinstance(amount, Decimal):
            raise TypeError(f"amount must be Decimal, got {type(amount).__name__} (I-01)")
        is_breach = amount > self._threshold
        return BreachDecision(
            is_breach=is_breach,
            breach_kind=self._breach_kind if is_breach else None,
            amount=amount,
            threshold=self._threshold,
        )
