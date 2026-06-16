"""Decimal-safe comparison primitives for safeguarding reconciliation.

Regime-agnostic. These functions encode the ONE arithmetic shared by every
reconciliation path: compute a signed/absolute difference and test it against a
penny-exact tolerance. They carry no thresholds and no regulatory meaning — the
caller supplies the tolerance.

Invariant I-01: money is Decimal only — never float. Each primitive guards its
inputs so a stray float can never silently corrupt a safeguarding comparison.
"""

from __future__ import annotations

from decimal import Decimal


def _require_decimal(name: str, value: Decimal) -> None:
    """Guard: reject non-Decimal money (I-01)."""
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be Decimal, got {type(value).__name__} (I-01)")


def signed_difference(left: Decimal, right: Decimal) -> Decimal:
    """Return ``left - right`` (signed). Positive ⇒ left exceeds right."""
    _require_decimal("left", left)
    _require_decimal("right", right)
    return left - right


def absolute_difference(left: Decimal, right: Decimal) -> Decimal:
    """Return ``|left - right|`` — the non-negative reconciliation magnitude."""
    return abs(signed_difference(left, right))


def within_tolerance(left: Decimal, right: Decimal, tolerance: Decimal) -> bool:
    """True iff ``|left - right| <= tolerance`` (penny-exact MATCH semantics).

    Boundary rule (shared by both CASS regimes): a difference EQUAL to the
    tolerance is *within* tolerance (matched). Only a strictly greater difference
    is out of tolerance. Mirrors ``not (BreachEvaluator.evaluate(...).is_breach)``.
    """
    _require_decimal("tolerance", tolerance)
    return absolute_difference(left, right) <= tolerance
