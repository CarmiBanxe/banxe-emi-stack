"""
tests/test_risk_management/test_risk_scorer.py
IL-RMS-01 | Phase 37 | banxe-emi-stack — 18 tests
"""

from __future__ import annotations

from decimal import Decimal

from services.risk_management.models import (
    InMemoryRiskScorePort,
    RiskCategory,
    RiskLevel,
    ScoreModel,
)
from services.risk_management.risk_scorer import RiskScorer


def _scorer() -> RiskScorer:
    return RiskScorer(InMemoryRiskScorePort())


class TestScoreEntity:
    def test_returns_risk_score(self) -> None:
        scorer = _scorer()
        result = scorer.score_entity("e-1", {"factor": Decimal("50")}, RiskCategory.AML)
        assert result.entity_id == "e-1"

    def test_score_is_decimal(self) -> None:
        scorer = _scorer()
        result = scorer.score_entity("e-1", {"f": Decimal("30")}, RiskCategory.CREDIT)
        assert isinstance(result.score, Decimal)

    def test_score_clamped_to_100(self) -> None:
        scorer = _scorer()
        result = scorer.score_entity("e-1", {"f": Decimal("999")}, RiskCategory.AML)
        assert result.score == Decimal("100")

    def test_score_clamped_to_zero(self) -> None:
        scorer = _scorer()
        result = scorer.score_entity("e-1", {"f": Decimal("-999")}, RiskCategory.AML)
        assert result.score == Decimal("0")

    def test_model_stored_correctly(self) -> None:
        scorer = _scorer()
        result = scorer.score_entity(
            "e-1", {"f": Decimal("10")}, RiskCategory.FRAUD, ScoreModel.MONTE_CARLO
        )
        assert result.model == ScoreModel.MONTE_CARLO

    def test_category_stored_correctly(self) -> None:
        scorer = _scorer()
        result = scorer.score_entity("e-1", {"f": Decimal("10")}, RiskCategory.CREDIT)
        assert result.category == RiskCategory.CREDIT

    def test_saved_to_store(self) -> None:
        store = InMemoryRiskScorePort()
        scorer = RiskScorer(store)
        scorer.score_entity("e-99", {"f": Decimal("10")}, RiskCategory.MARKET)
        scores = store.get_scores("e-99")
        assert len(scores) == 1

    def test_empty_factors_returns_zero(self) -> None:
        scorer = _scorer()
        result = scorer.score_entity("e-1", {}, RiskCategory.AML)
        assert result.score == Decimal("0")


class TestComputeAggregate:
    def test_empty_list_returns_zero(self) -> None:
        scorer = _scorer()
        assert scorer.compute_aggregate([]) == Decimal("0")

    def test_single_score_returns_value(self) -> None:
        scorer = _scorer()
        s = scorer.score_entity("e-1", {"f": Decimal("50")}, RiskCategory.AML)
        agg = scorer.compute_aggregate([s])
        assert agg > Decimal("0")

    def test_aggregate_is_decimal(self) -> None:
        scorer = _scorer()
        s = scorer.score_entity("e-1", {"f": Decimal("40")}, RiskCategory.CREDIT)
        assert isinstance(scorer.compute_aggregate([s]), Decimal)


class TestClassifyLevel:
    def test_below_25_is_low(self) -> None:
        scorer = _scorer()
        assert scorer.classify_level(Decimal("0")) == RiskLevel.LOW

    def test_exactly_25_is_medium(self) -> None:
        scorer = _scorer()
        assert scorer.classify_level(Decimal("25")) == RiskLevel.MEDIUM

    def test_just_below_25_is_low(self) -> None:
        scorer = _scorer()
        assert scorer.classify_level(Decimal("24.99")) == RiskLevel.LOW

    def test_exactly_50_is_high(self) -> None:
        scorer = _scorer()
        assert scorer.classify_level(Decimal("50")) == RiskLevel.HIGH

    def test_just_below_50_is_medium(self) -> None:
        scorer = _scorer()
        assert scorer.classify_level(Decimal("49.99")) == RiskLevel.MEDIUM

    def test_exactly_75_is_critical(self) -> None:
        scorer = _scorer()
        assert scorer.classify_level(Decimal("75")) == RiskLevel.CRITICAL

    def test_just_below_75_is_high(self) -> None:
        scorer = _scorer()
        assert scorer.classify_level(Decimal("74.99")) == RiskLevel.HIGH

    def test_100_is_critical(self) -> None:
        scorer = _scorer()
        assert scorer.classify_level(Decimal("100")) == RiskLevel.CRITICAL


class TestBatchScore:
    def test_returns_list(self) -> None:
        scorer = _scorer()
        results = scorer.batch_score(
            [
                {"entity_id": "e-1", "factors": {"f": "30"}, "category": "AML"},
                {"entity_id": "e-2", "factors": {"f": "60"}, "category": "CREDIT"},
            ]
        )
        assert len(results) == 2

    def test_entity_ids_correct(self) -> None:
        scorer = _scorer()
        results = scorer.batch_score(
            [
                {"entity_id": "e-a", "factors": {"f": "20"}, "category": "FRAUD"},
            ]
        )
        assert results[0].entity_id == "e-a"

    def test_empty_batch_returns_empty(self) -> None:
        scorer = _scorer()
        assert scorer.batch_score([]) == []
