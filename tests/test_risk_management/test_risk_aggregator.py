"""
tests/test_risk_management/test_risk_aggregator.py
IL-RMS-01 | Phase 37 | banxe-emi-stack — 18 tests
"""

from __future__ import annotations

from decimal import Decimal

from services.risk_management.models import (
    AssessmentStatus,
    InMemoryAssessmentPort,
    InMemoryRiskScorePort,
    RiskCategory,
)
from services.risk_management.risk_aggregator import RiskAggregator
from services.risk_management.risk_scorer import RiskScorer


def _make_aggregator() -> tuple[RiskAggregator, InMemoryRiskScorePort]:
    store = InMemoryRiskScorePort()
    # clear seeded data
    store._scores.clear()
    aggregator = RiskAggregator(score_store=store, assessment_store=InMemoryAssessmentPort())
    return aggregator, store


class TestAggregateEntity:
    def test_returns_assessment(self) -> None:
        agg, store = _make_aggregator()
        scorer = RiskScorer(store)
        scorer.score_entity("e-1", {"f": Decimal("50")}, RiskCategory.AML)
        assessment = agg.aggregate_entity("e-1")
        assert assessment.entity_id == "e-1"

    def test_status_is_completed(self) -> None:
        agg, store = _make_aggregator()
        scorer = RiskScorer(store)
        scorer.score_entity("e-1", {"f": Decimal("40")}, RiskCategory.CREDIT)
        assessment = agg.aggregate_entity("e-1")
        assert assessment.status == AssessmentStatus.COMPLETED

    def test_aggregate_score_is_decimal(self) -> None:
        agg, store = _make_aggregator()
        scorer = RiskScorer(store)
        scorer.score_entity("e-1", {"f": Decimal("30")}, RiskCategory.FRAUD)
        assessment = agg.aggregate_entity("e-1")
        assert isinstance(assessment.aggregate_score, Decimal)

    def test_empty_entity_returns_zero_aggregate(self) -> None:
        agg, _ = _make_aggregator()
        assessment = agg.aggregate_entity("no-entity")
        assert assessment.aggregate_score == Decimal("0")

    def test_scores_list_populated(self) -> None:
        agg, store = _make_aggregator()
        scorer = RiskScorer(store)
        scorer.score_entity("e-1", {"f": Decimal("20")}, RiskCategory.MARKET)
        assessment = agg.aggregate_entity("e-1")
        assert len(assessment.scores) >= 1


class TestPortfolioHeatmap:
    def test_returns_dict(self) -> None:
        agg, store = _make_aggregator()
        scorer = RiskScorer(store)
        scorer.score_entity("e-1", {"f": Decimal("30")}, RiskCategory.AML)
        result = agg.portfolio_heatmap(["e-1"])
        assert "e-1" in result

    def test_entity_has_category_levels(self) -> None:
        agg, store = _make_aggregator()
        scorer = RiskScorer(store)
        scorer.score_entity("e-2", {"f": Decimal("60")}, RiskCategory.FRAUD)
        result = agg.portfolio_heatmap(["e-2"])
        assert "FRAUD" in result["e-2"]

    def test_empty_entity_ids_returns_empty(self) -> None:
        agg, _ = _make_aggregator()
        assert agg.portfolio_heatmap([]) == {}

    def test_multiple_entities(self) -> None:
        agg, store = _make_aggregator()
        scorer = RiskScorer(store)
        scorer.score_entity("e-1", {"f": Decimal("30")}, RiskCategory.AML)
        scorer.score_entity("e-2", {"f": Decimal("40")}, RiskCategory.CREDIT)
        result = agg.portfolio_heatmap(["e-1", "e-2"])
        assert len(result) == 2


class TestConcentrationAnalysis:
    def test_returns_dict_with_distribution(self) -> None:
        agg, _ = _make_aggregator()
        result = agg.concentration_analysis()
        assert "distribution" in result

    def test_total_entities_correct(self) -> None:
        agg, store = _make_aggregator()
        scorer = RiskScorer(store)
        scorer.score_entity("e-1", {"f": Decimal("30")}, RiskCategory.AML)
        scorer.score_entity("e-2", {"f": Decimal("40")}, RiskCategory.AML)
        result = agg.concentration_analysis()
        assert result["total_entities"] >= 2

    def test_concentration_flag_over_20pct(self) -> None:
        agg, store = _make_aggregator()
        scorer = RiskScorer(store)
        # FRAUD weight is 0.15; need score >= 75 → factor >= 500
        for i in range(3):
            scorer.score_entity(f"e-crit-{i}", {"f": Decimal("600")}, RiskCategory.FRAUD)
        scorer.score_entity("e-low", {"f": Decimal("1")}, RiskCategory.FRAUD)
        result = agg.concentration_analysis()
        assert result["concentration_flag"] is True

    def test_no_flag_when_all_low(self) -> None:
        agg, store = _make_aggregator()
        scorer = RiskScorer(store)
        for i in range(10):
            scorer.score_entity(f"e-{i}", {"f": Decimal("1")}, RiskCategory.MARKET)
        result = agg.concentration_analysis()
        assert result["concentration_flag"] is False


class TestGetTopRisks:
    def test_returns_list(self) -> None:
        agg, _ = _make_aggregator()
        result = agg.get_top_risks(5)
        assert isinstance(result, list)

    def test_sorted_descending(self) -> None:
        agg, store = _make_aggregator()
        scorer = RiskScorer(store)
        scorer.score_entity("e-hi", {"f": Decimal("300")}, RiskCategory.FRAUD)
        scorer.score_entity("e-lo", {"f": Decimal("1")}, RiskCategory.CREDIT)
        result = agg.get_top_risks(10)
        scores = [r.score for r in result]
        assert scores == sorted(scores, reverse=True)

    def test_n_limits_results(self) -> None:
        agg, store = _make_aggregator()
        scorer = RiskScorer(store)
        for i in range(5):
            scorer.score_entity(f"e-{i}", {"f": Decimal("20")}, RiskCategory.AML)
        result = agg.get_top_risks(3)
        assert len(result) <= 3
