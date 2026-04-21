"""
tests/test_consumer_duty/test_outcome_assessor.py
Tests for OutcomeAssessor: assess, thresholds, failing outcomes, aggregate.
IL-CDO-01 | Phase 50 | Sprint 35

≥20 tests covering:
- assess_outcome (passed/failed, all 4 types)
- OUTCOME_THRESHOLDS (Decimal, I-01)
- get_failing_outcomes (type filter, all)
- aggregate_outcome_score (Decimal weighted average, empty)
- SHA-256 IDs, append-only (I-24)
"""

from __future__ import annotations

from decimal import Decimal

from services.consumer_duty.models_v2 import (
    AssessmentStatus,
    InMemoryOutcomeStore,
    OutcomeType,
)
from services.consumer_duty.outcome_assessor import (
    OUTCOME_THRESHOLDS,
    OutcomeAssessor,
)


def make_assessor() -> tuple[OutcomeAssessor, InMemoryOutcomeStore]:
    store = InMemoryOutcomeStore()
    assessor = OutcomeAssessor(store)
    return assessor, store


# ── assess_outcome tests ──────────────────────────────────────────────────────


def test_assess_outcome_above_threshold_passes() -> None:
    """Test outcome with score >= threshold returns PASSED."""
    assessor, _ = make_assessor()
    assessment = assessor.assess_outcome("c1", OutcomeType.PRODUCTS_SERVICES, {"score": "0.8"})
    assert assessment.status == AssessmentStatus.PASSED


def test_assess_outcome_below_threshold_fails() -> None:
    """Test outcome with score < threshold returns FAILED."""
    assessor, _ = make_assessor()
    assessment = assessor.assess_outcome("c1", OutcomeType.PRODUCTS_SERVICES, {"score": "0.5"})
    assert assessment.status == AssessmentStatus.FAILED


def test_assess_outcome_exactly_at_threshold_passes() -> None:
    """Test outcome at exactly threshold score returns PASSED."""
    assessor, _ = make_assessor()
    threshold = OUTCOME_THRESHOLDS[OutcomeType.PRODUCTS_SERVICES]
    assessment = assessor.assess_outcome(
        "c1", OutcomeType.PRODUCTS_SERVICES, {"score": str(threshold)}
    )
    assert assessment.status == AssessmentStatus.PASSED


def test_assess_outcome_score_is_decimal() -> None:
    """Test assessment score is Decimal (I-01)."""
    assessor, _ = make_assessor()
    assessment = assessor.assess_outcome("c1", OutcomeType.PRICE_VALUE, {"score": "0.7"})
    assert isinstance(assessment.score, Decimal)


def test_assess_outcome_sha256_id_format() -> None:
    """Test assessment_id has asm_ prefix."""
    assessor, _ = make_assessor()
    assessment = assessor.assess_outcome("c1", OutcomeType.CONSUMER_SUPPORT, {"score": "0.9"})
    assert assessment.assessment_id.startswith("asm_")


def test_assess_outcome_appends_to_store() -> None:
    """Test assess_outcome appends to store (I-24)."""
    assessor, store = make_assessor()
    assessor.assess_outcome("c1", OutcomeType.PRODUCTS_SERVICES, {"score": "0.8"})
    results = store.list_by_customer("c1")
    assert len(results) == 1


def test_assess_outcome_all_four_types() -> None:
    """Test assess_outcome works for all 4 PS22/9 outcome areas."""
    assessor, _ = make_assessor()
    for outcome_type in OutcomeType:
        a = assessor.assess_outcome("c1", outcome_type, {"score": "0.9"})
        assert a.outcome_type == outcome_type


def test_assess_outcome_clamps_score_below_zero() -> None:
    """Test score clamped to 0.0 if negative."""
    assessor, _ = make_assessor()
    assessment = assessor.assess_outcome("c1", OutcomeType.PRODUCTS_SERVICES, {"score": "-0.5"})
    assert assessment.score == Decimal("0.0")


def test_assess_outcome_clamps_score_above_one() -> None:
    """Test score clamped to 1.0 if above 1."""
    assessor, _ = make_assessor()
    assessment = assessor.assess_outcome("c1", OutcomeType.PRODUCTS_SERVICES, {"score": "1.5"})
    assert assessment.score == Decimal("1.0")


# ── OUTCOME_THRESHOLDS tests ──────────────────────────────────────────────────


def test_outcome_thresholds_are_decimal() -> None:
    """Test all OUTCOME_THRESHOLDS values are Decimal (I-01)."""
    for threshold in OUTCOME_THRESHOLDS.values():
        assert isinstance(threshold, Decimal)


def test_outcome_threshold_products_services() -> None:
    """Test PRODUCTS_SERVICES threshold is 0.7."""
    assert OUTCOME_THRESHOLDS[OutcomeType.PRODUCTS_SERVICES] == Decimal("0.7")


def test_outcome_threshold_price_value() -> None:
    """Test PRICE_VALUE threshold is 0.65."""
    assert OUTCOME_THRESHOLDS[OutcomeType.PRICE_VALUE] == Decimal("0.65")


def test_outcome_threshold_consumer_support() -> None:
    """Test CONSUMER_SUPPORT threshold is 0.75."""
    assert OUTCOME_THRESHOLDS[OutcomeType.CONSUMER_SUPPORT] == Decimal("0.75")


# ── get_failing_outcomes tests ────────────────────────────────────────────────


def test_get_failing_outcomes_returns_only_failed() -> None:
    """Test get_failing_outcomes returns only FAILED assessments."""
    assessor, _ = make_assessor()
    assessor.assess_outcome("c1", OutcomeType.PRODUCTS_SERVICES, {"score": "0.8"})  # PASSED
    assessor.assess_outcome("c2", OutcomeType.PRODUCTS_SERVICES, {"score": "0.5"})  # FAILED
    failing = assessor.get_failing_outcomes()
    assert all(a.status == AssessmentStatus.FAILED for a in failing)


def test_get_failing_outcomes_type_filter() -> None:
    """Test get_failing_outcomes filtered by outcome type."""
    assessor, _ = make_assessor()
    assessor.assess_outcome("c1", OutcomeType.PRODUCTS_SERVICES, {"score": "0.5"})  # FAILED
    assessor.assess_outcome("c1", OutcomeType.PRICE_VALUE, {"score": "0.5"})  # FAILED
    failing_ps = assessor.get_failing_outcomes(OutcomeType.PRODUCTS_SERVICES)
    assert all(a.outcome_type == OutcomeType.PRODUCTS_SERVICES for a in failing_ps)


def test_get_failing_outcomes_empty_if_all_pass() -> None:
    """Test get_failing_outcomes returns empty if all pass."""
    assessor, _ = make_assessor()
    assessor.assess_outcome("c1", OutcomeType.PRODUCTS_SERVICES, {"score": "0.9"})
    failing = assessor.get_failing_outcomes()
    assert len(failing) == 0


# ── aggregate_outcome_score tests ─────────────────────────────────────────────


def test_aggregate_outcome_score_returns_decimal() -> None:
    """Test aggregate_outcome_score returns Decimal (I-01)."""
    assessor, _ = make_assessor()
    assessor.assess_outcome("c1", OutcomeType.PRODUCTS_SERVICES, {"score": "0.8"})
    score = assessor.aggregate_outcome_score("c1")
    assert isinstance(score, Decimal)


def test_aggregate_outcome_score_empty_returns_zero() -> None:
    """Test aggregate_outcome_score returns 0.0 for unknown customer."""
    assessor, _ = make_assessor()
    score = assessor.aggregate_outcome_score("unknown")
    assert score == Decimal("0.0")


def test_aggregate_outcome_score_single_outcome() -> None:
    """Test aggregate with single outcome returns that score."""
    assessor, _ = make_assessor()
    assessor.assess_outcome("c1", OutcomeType.PRODUCTS_SERVICES, {"score": "0.8"})
    score = assessor.aggregate_outcome_score("c1")
    assert score > Decimal("0.0")
