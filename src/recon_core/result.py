"""Common reconciliation result value type both regimes map to/from.

``CoreReconResult`` is a neutral, regime-agnostic carrier for a single
balance-pair reconciliation: the two compared amounts, their signed and absolute
difference, and the breach decision produced by a :class:`BreachEvaluator`.

It is NOT a replacement for the regime-specific public result types
(``ReconciliationResult`` for CASS 15, ``ReconciliationReport`` for CASS 7.15).
Each regime MAPS to/from this internally and keeps its own public schema, status
enum, and reporting artefacts unchanged.

Invariant I-01: Decimal money only.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .breach_evaluator import BreachEvaluator
from .compare import signed_difference


@dataclass(frozen=True)
class CoreReconResult:
    """Neutral outcome of comparing one balance pair under one evaluator."""

    left: Decimal
    right: Decimal
    difference: Decimal  # signed: left - right
    abs_difference: Decimal
    is_breach: bool
    breach_kind: str | None
    threshold: Decimal


def evaluate_balances(
    left: Decimal,
    right: Decimal,
    evaluator: BreachEvaluator,
) -> CoreReconResult:
    """Compare ``left`` vs ``right`` and classify via ``evaluator``.

    The signed difference (``left - right``) is preserved for the caller (e.g. to
    tell shortfall from surplus); the breach decision uses the absolute magnitude.
    """
    diff = signed_difference(left, right)
    abs_diff = abs(diff)
    decision = evaluator.evaluate(abs_diff)
    return CoreReconResult(
        left=left,
        right=right,
        difference=diff,
        abs_difference=abs_diff,
        is_breach=decision.is_breach,
        breach_kind=decision.breach_kind,
        threshold=evaluator.threshold,
    )
