"""CostEstimator — Decimal/token estimate + cap-awareness (no float, ADR-047)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.agents._lineage import BudgetBreach, CostCap, RequestCost
from services.producers.cost_estimator import CostEstimator
from services.producers.ports import DEFAULT_COST_CAP


def _cap() -> CostCap:
    return CostCap(
        max_request_tokens=1_000,
        max_request_cost=Decimal("0.10"),
        max_window_tokens=100_000,
        max_window_cost=Decimal("10.00"),
    )


class _LiveSource:
    def __init__(self, cost: RequestCost | None) -> None:
        self._cost = cost

    def usage_for(self, accounting_key: str) -> RequestCost | None:
        return self._cost


def test_static_estimate_is_decimal() -> None:
    est = CostEstimator(cost_cap=DEFAULT_COST_CAP, price_per_1k_tokens=Decimal("0.015"))
    out = est.estimate("act", est_tokens=2000)
    assert out.cost == RequestCost(tokens=2000, cost=Decimal("0.030000"))
    assert isinstance(out.cost.cost, Decimal)
    assert out.breach is BudgetBreach.NONE


def test_zero_tokens() -> None:
    est = CostEstimator(cost_cap=DEFAULT_COST_CAP)
    out = est.estimate("act", est_tokens=0)
    assert out.cost.cost == Decimal("0.000000")


def test_negative_tokens_rejected() -> None:
    est = CostEstimator(cost_cap=DEFAULT_COST_CAP)
    with pytest.raises(ValueError, match="non-negative"):
        est.estimate("act", est_tokens=-1)


def test_breach_on_tokens() -> None:
    est = CostEstimator(cost_cap=_cap(), price_per_1k_tokens=Decimal("0.0001"))
    assert est.estimate("act", est_tokens=1_001).breach is BudgetBreach.BREACH


def test_breach_on_cost() -> None:
    est = CostEstimator(cost_cap=_cap(), price_per_1k_tokens=Decimal("1.0"))
    # 500 tokens × £1/1k = £0.50 > £0.10 cap → BREACH (token count under cap).
    out = est.estimate("act", est_tokens=500)
    assert out.breach is BudgetBreach.BREACH


def test_warn_band_on_tokens() -> None:
    est = CostEstimator(cost_cap=_cap(), price_per_1k_tokens=Decimal("0.00001"))
    # 800 tokens = 80% of 1000 cap → WARN.
    assert est.estimate("act", est_tokens=800).breach is BudgetBreach.WARN


def test_none_band_under_warn() -> None:
    est = CostEstimator(cost_cap=_cap(), price_per_1k_tokens=Decimal("0.00001"))
    assert est.estimate("act", est_tokens=700).breach is BudgetBreach.NONE


def test_live_source_used_when_keyed() -> None:
    live = RequestCost(tokens=42, cost=Decimal("0.999999"))
    est = CostEstimator(cost_cap=DEFAULT_COST_CAP, source=_LiveSource(live))
    out = est.estimate("act", est_tokens=9999, accounting_key="key-1")
    assert out.cost == live  # live figure wins over the static estimate


def test_live_source_none_falls_back_to_static() -> None:
    est = CostEstimator(
        cost_cap=DEFAULT_COST_CAP,
        price_per_1k_tokens=Decimal("0.015"),
        source=_LiveSource(None),
    )
    out = est.estimate("act", est_tokens=1000, accounting_key="key-1")
    assert out.cost.tokens == 1000  # static fallback


def test_no_accounting_key_skips_source() -> None:
    # A live source is present but no key is given → static path only.
    est = CostEstimator(
        cost_cap=DEFAULT_COST_CAP,
        source=_LiveSource(RequestCost(tokens=1, cost=Decimal("9"))),
    )
    out = est.estimate("act", est_tokens=1000)
    assert out.cost.tokens == 1000
