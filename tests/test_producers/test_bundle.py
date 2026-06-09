"""ProducerBundle — composition-root entry point producing the 3 agent inputs."""

from __future__ import annotations

from decimal import Decimal

from services.agents._lineage import BudgetBreach, ComplianceResult, RequestCost
from services.intent_layer.models import MatchSource
from services.producers.bundle import ProducerBundle
from services.producers.compliance_producer import ComplianceProducer
from services.producers.confidence_scorer import ConfidenceScorer, ScoringSignals
from services.producers.cost_estimator import CostEstimator
from services.producers.ports import DEFAULT_COST_CAP
from tests.test_producers.conftest import StubCheck, make_request


def test_null_bundle_produces_pass_and_cost() -> None:
    bundle = ProducerBundle.null()
    out = bundle.produce(
        check_request=make_request(),
        signals=ScoringSignals(match_source=MatchSource.EXACT),
        est_tokens=1000,
    )
    assert out.compliance_result is ComplianceResult.PASS
    assert out.confidence_score == 1.0
    assert isinstance(out.request_cost, RequestCost)
    assert out.budget_breach is BudgetBreach.NONE
    assert out.verdict.result is ComplianceResult.PASS


def test_wired_bundle_propagates_fail() -> None:
    # A wired bundle with a FAIL sanctions port yields FAIL into the agent param.
    bundle = ProducerBundle(
        compliance=ComplianceProducer(sanctions=StubCheck(ComplianceResult.FAIL)),
        confidence=ConfidenceScorer(),
        cost=CostEstimator(cost_cap=DEFAULT_COST_CAP),
    )
    out = bundle.produce(
        check_request=make_request(amount=Decimal("250000")),
        signals=ScoringSignals(match_source=MatchSource.LLM, risk_class="HIGH"),
        est_tokens=500,
    )
    assert out.compliance_result is ComplianceResult.FAIL
    assert out.confidence_score == 0.60
    assert out.request_cost.tokens == 500


def test_bundle_passes_accounting_key_through() -> None:
    bundle = ProducerBundle.null()
    out = bundle.produce(
        check_request=make_request(),
        signals=ScoringSignals(match_source=MatchSource.EXACT),
        est_tokens=100,
        accounting_key="tenant-1",
    )
    assert out.request_cost.tokens == 100
