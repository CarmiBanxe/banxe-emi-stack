"""
tests/test_audit_dashboard/test_risk_scorer.py
IL-AGD-01 | Phase 16

Async tests for RiskScorer — 20 tests.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from services.audit_dashboard.audit_aggregator import AuditAggregator
from services.audit_dashboard.models import (
    AuditEvent,
    EventCategory,
    InMemoryEventStore,
    InMemoryRiskEngine,
    RiskLevel,
    RiskScore,
)
from services.audit_dashboard.risk_scorer import RiskScorer

_NOW = datetime.now(UTC)


def _make_scorer(store: InMemoryEventStore | None = None) -> RiskScorer:
    s = store or InMemoryEventStore()
    return RiskScorer(engine=InMemoryRiskEngine(), store=s)


def _make_scorer_and_aggregator() -> tuple[RiskScorer, AuditAggregator, InMemoryEventStore]:
    store = InMemoryEventStore()
    scorer = RiskScorer(engine=InMemoryRiskEngine(), store=store)
    aggregator = AuditAggregator(store=store)
    return scorer, aggregator, store


async def _ingest(
    store: InMemoryEventStore,
    entity_id: str,
    risk_level: RiskLevel = RiskLevel.LOW,
) -> None:
    event = AuditEvent(
        id=str(id(object())),
        category=EventCategory.AML,
        event_type="check",
        entity_id=entity_id,
        actor="a",
        details={},
        risk_level=risk_level,
        created_at=datetime.now(UTC),
        source_service="svc",
    )
    await store.ingest(event)


# ── score_entity ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_score_entity_returns_risk_score_with_entity_id():
    scorer = _make_scorer()
    score = await scorer.score_entity("entity-42")
    assert isinstance(score, RiskScore)
    assert score.entity_id == "entity-42"


@pytest.mark.asyncio
async def test_score_entity_all_score_fields_are_float():
    scorer = _make_scorer()
    score = await scorer.score_entity("e-float")
    for field in [
        score.aml_score,
        score.fraud_score,
        score.operational_score,
        score.regulatory_score,
        score.overall_score,
    ]:
        assert isinstance(field, float), f"Expected float, got {type(field)}"
        assert 0.0 <= field <= 100.0


@pytest.mark.asyncio
async def test_score_entity_with_no_events_is_low_risk():
    scorer = _make_scorer()
    score = await scorer.score_entity("entity-clean")
    level = scorer.categorise_risk(score)
    assert level == RiskLevel.LOW


@pytest.mark.asyncio
async def test_score_entity_with_critical_events_has_higher_overall_score():
    store = InMemoryEventStore()
    scorer = RiskScorer(engine=InMemoryRiskEngine(), store=store)
    for _ in range(5):
        await _ingest(store, "risky-entity", RiskLevel.CRITICAL)
    score = await scorer.score_entity("risky-entity")
    baseline = await RiskScorer(
        engine=InMemoryRiskEngine(), store=InMemoryEventStore()
    ).score_entity("clean")
    assert score.overall_score > baseline.overall_score


# ── categorise_risk ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_categorise_risk_low_when_below_25():
    scorer = _make_scorer()
    score = RiskScore(
        entity_id="e",
        computed_at=_NOW,
        aml_score=10.0,
        fraud_score=10.0,
        operational_score=10.0,
        regulatory_score=10.0,
        overall_score=10.0,
        contributing_factors=[],
    )
    assert scorer.categorise_risk(score) == RiskLevel.LOW


@pytest.mark.asyncio
async def test_categorise_risk_medium_when_25_to_49():
    scorer = _make_scorer()
    score = RiskScore(
        entity_id="e",
        computed_at=_NOW,
        aml_score=30.0,
        fraud_score=30.0,
        operational_score=30.0,
        regulatory_score=30.0,
        overall_score=35.0,
        contributing_factors=[],
    )
    assert scorer.categorise_risk(score) == RiskLevel.MEDIUM


@pytest.mark.asyncio
async def test_categorise_risk_high_when_50_to_74():
    scorer = _make_scorer()
    score = RiskScore(
        entity_id="e",
        computed_at=_NOW,
        aml_score=60.0,
        fraud_score=60.0,
        operational_score=60.0,
        regulatory_score=60.0,
        overall_score=60.0,
        contributing_factors=[],
    )
    assert scorer.categorise_risk(score) == RiskLevel.HIGH


@pytest.mark.asyncio
async def test_categorise_risk_critical_when_75_plus():
    scorer = _make_scorer()
    score = RiskScore(
        entity_id="e",
        computed_at=_NOW,
        aml_score=80.0,
        fraud_score=80.0,
        operational_score=80.0,
        regulatory_score=80.0,
        overall_score=80.0,
        contributing_factors=[],
    )
    assert scorer.categorise_risk(score) == RiskLevel.CRITICAL


# ── score_batch ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_score_batch_two_entities_returns_two_scores():
    scorer = _make_scorer()
    scores = await scorer.score_batch(["e1", "e2"])
    assert len(scores) == 2
    assert scores[0].entity_id == "e1"
    assert scores[1].entity_id == "e2"


@pytest.mark.asyncio
async def test_score_batch_empty_returns_empty_list():
    scorer = _make_scorer()
    scores = await scorer.score_batch([])
    assert scores == []


@pytest.mark.asyncio
async def test_score_batch_three_entities_returns_three_scores():
    scorer = _make_scorer()
    scores = await scorer.score_batch(["a", "b", "c"])
    assert len(scores) == 3


# ── get_risk_summary ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_risk_summary_returns_by_level_dict():
    scorer = _make_scorer()
    summary = await scorer.get_risk_summary(["e1", "e2"])
    assert "by_level" in summary
    assert isinstance(summary["by_level"], dict)


@pytest.mark.asyncio
async def test_get_risk_summary_total_equals_len_entity_ids():
    scorer = _make_scorer()
    entity_ids = ["e1", "e2", "e3"]
    summary = await scorer.get_risk_summary(entity_ids)
    assert summary["total"] == len(entity_ids)


@pytest.mark.asyncio
async def test_get_risk_summary_empty_list_returns_zeros():
    scorer = _make_scorer()
    summary = await scorer.get_risk_summary([])
    assert summary["total"] == 0
    assert all(v == 0 for v in summary["by_level"].values())


# ── other ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_contributing_factors_is_list():
    scorer = _make_scorer()
    score = await scorer.score_entity("e-factors")
    assert isinstance(score.contributing_factors, list)


@pytest.mark.asyncio
async def test_score_entity_lookback_days_7():
    scorer = _make_scorer()
    score = await scorer.score_entity("e-short", lookback_days=7)
    assert isinstance(score, RiskScore)


@pytest.mark.asyncio
async def test_score_entity_with_high_risk_events():
    store = InMemoryEventStore()
    scorer = RiskScorer(engine=InMemoryRiskEngine(), store=store)
    for _ in range(3):
        await _ingest(store, "high-entity", RiskLevel.HIGH)
    score = await scorer.score_entity("high-entity")
    assert score.overall_score > 0.0


@pytest.mark.asyncio
async def test_multiple_calls_same_entity_are_consistent():
    scorer = _make_scorer()
    score1 = await scorer.score_entity("consistent-entity")
    score2 = await scorer.score_entity("consistent-entity")
    assert score1.overall_score == score2.overall_score


@pytest.mark.asyncio
async def test_get_high_risk_entities_returns_list():
    scorer = _make_scorer()
    result = await scorer.get_high_risk_entities()
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_score_entity_computed_at_is_recent():
    scorer = _make_scorer()
    score = await scorer.score_entity("recent-entity")
    delta = datetime.now(UTC) - score.computed_at
    assert delta.total_seconds() < 1.0
