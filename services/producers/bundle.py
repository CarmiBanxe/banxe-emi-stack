"""
services/producers/bundle.py — ProducerBundle (S5.2).

The single object the composition root uses to populate the three INJECTED agent
inputs before invoking an L2 agent. It runs the compliance / confidence / cost
producers and returns :class:`ProducerOutputs`, whose fields map 1:1 onto the
agents' existing keyword params:

    outputs = bundle.produce(...)
    await agent.do_action(
        intent,                                   # carries confidence_score + request_cost
        compliance_result=outputs.compliance_result,   # ← REPLACES default-PASS
    )

NO agent is edited — the bundle only PRODUCES values that flow into the seam that
already exists. ``ProducerBundle.null()`` is the safe pre-wiring default (all
PASS); the WIRED composition builds it with real adapters (see ``adapters.py``
and ``WIRING.md``).
"""

from __future__ import annotations

from dataclasses import dataclass

from services.agents._lineage import BudgetBreach, ComplianceResult, RequestCost
from services.producers.compliance_producer import ComplianceProducer, ComplianceVerdict
from services.producers.confidence_scorer import ConfidenceScorer, ScoringSignals
from services.producers.cost_estimator import CostEstimator
from services.producers.ports import DEFAULT_COST_CAP, ComplianceCheckRequest


@dataclass(frozen=True)
class ProducerOutputs:
    """The three produced agent inputs + diagnostics (no PII)."""

    compliance_result: ComplianceResult
    confidence_score: float
    request_cost: RequestCost
    budget_breach: BudgetBreach
    verdict: ComplianceVerdict


class ProducerBundle:
    """Bundles the three producers behind one ``produce(...)`` call."""

    def __init__(
        self,
        *,
        compliance: ComplianceProducer,
        confidence: ConfidenceScorer,
        cost: CostEstimator,
    ) -> None:
        self._compliance = compliance
        self._confidence = confidence
        self._cost = cost

    def produce(
        self,
        *,
        check_request: ComplianceCheckRequest,
        signals: ScoringSignals,
        est_tokens: int,
        accounting_key: str | None = None,
    ) -> ProducerOutputs:
        """Run all three producers for one agent invocation."""
        verdict = self._compliance.evaluate(check_request)
        confidence = self._confidence.score(signals)
        estimate = self._cost.estimate(
            check_request.action, est_tokens=est_tokens, accounting_key=accounting_key
        )
        return ProducerOutputs(
            compliance_result=verdict.result,
            confidence_score=confidence,
            request_cost=estimate.cost,
            budget_breach=estimate.breach,
            verdict=verdict,
        )

    @classmethod
    def null(cls) -> ProducerBundle:
        """Pre-wiring default: Null compliance ports (PASS) + static cost source."""
        return cls(
            compliance=ComplianceProducer(),
            confidence=ConfidenceScorer(),
            cost=CostEstimator(cost_cap=DEFAULT_COST_CAP),
        )


__all__ = ["ProducerBundle", "ProducerOutputs"]
