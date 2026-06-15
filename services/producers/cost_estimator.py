"""
services/producers/cost_estimator.py — CostEstimator (S5.2, ADR-047 §D2).

Produces the ``request_cost`` (:class:`RequestCost` = tokens + Decimal amount)
the L2 agents accept, and a cap-awareness :class:`BudgetBreach` flag. Money is
ALWAYS :class:`~decimal.Decimal` — never float (ADR-047 §D2 / house rule).

Source of truth, in order:
  1. live S1-gateway per-key accounting via the injected :class:`CostSourcePort`
     (when ``accounting_key`` is given and the gateway has a figure);
  2. otherwise a deterministic static estimate ``tokens × price_per_1k / 1000``.

Cap-awareness compares the cost against an ADR-047 :class:`CostCap` in BOTH the
token and monetary dimensions → NONE / WARN / BREACH.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from services.agents._lineage import BudgetBreach, CostCap, RequestCost
from services.producers.ports import (
    DEFAULT_PRICE_PER_1K_TOKENS,
    CostSourcePort,
    StaticCostSource,
)

_ONE_K = Decimal("1000")
_CENTI_MICRO = Decimal("0.000001")  # 6dp monetary quantum


@dataclass(frozen=True)
class CostEstimate:
    """Produced cost for one agent invocation + its cap-awareness flag."""

    cost: RequestCost
    breach: BudgetBreach


class CostEstimator:
    """Deterministic producer of :class:`RequestCost` with cost-cap awareness."""

    def __init__(
        self,
        *,
        cost_cap: CostCap,
        price_per_1k_tokens: Decimal = DEFAULT_PRICE_PER_1K_TOKENS,
        source: CostSourcePort | None = None,
        warn_ratio: Decimal = Decimal("0.8"),
    ) -> None:
        self._cap = cost_cap
        self._price = price_per_1k_tokens
        self._source: CostSourcePort = source or StaticCostSource()
        self._warn_ratio = warn_ratio

    def estimate(
        self, action: str, *, est_tokens: int, accounting_key: str | None = None
    ) -> CostEstimate:
        """Estimate cost for ``action``; prefer live S1 accounting when available."""
        if est_tokens < 0:
            raise ValueError("est_tokens must be non-negative")
        cost = self._live_cost(accounting_key) or self._static_cost(est_tokens)
        return CostEstimate(cost=cost, breach=self._breach(cost))

    def _live_cost(self, accounting_key: str | None) -> RequestCost | None:
        if accounting_key is None:
            return None
        return self._source.usage_for(accounting_key)

    def _static_cost(self, est_tokens: int) -> RequestCost:
        amount = (Decimal(est_tokens) / _ONE_K * self._price).quantize(_CENTI_MICRO)
        return RequestCost(tokens=est_tokens, cost=amount)

    def _breach(self, cost: RequestCost) -> BudgetBreach:
        if cost.tokens > self._cap.max_request_tokens or cost.cost > self._cap.max_request_cost:
            return BudgetBreach.BREACH
        token_warn = Decimal(self._cap.max_request_tokens) * self._warn_ratio
        cost_warn = self._cap.max_request_cost * self._warn_ratio
        if Decimal(cost.tokens) >= token_warn or cost.cost >= cost_warn:
            return BudgetBreach.WARN
        return BudgetBreach.NONE


__all__ = ["CostEstimate", "CostEstimator"]
