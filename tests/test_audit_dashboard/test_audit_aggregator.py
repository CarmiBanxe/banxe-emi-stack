"""
tests/test_audit_dashboard/test_audit_aggregator.py
IL-AGD-01 | Phase 16

Async tests for AuditAggregator — 20 tests.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from services.audit_dashboard.audit_aggregator import AuditAggregator
from services.audit_dashboard.models import (
    AuditEvent,
    EventCategory,
    InMemoryEventStore,
    RiskLevel,
)

_NOW = datetime.now(UTC)


def _make_store() -> InMemoryEventStore:
    return InMemoryEventStore()


def _make_aggregator(store: InMemoryEventStore | None = None) -> AuditAggregator:
    return AuditAggregator(store=store or _make_store())


async def _ingest_simple(
    agg: AuditAggregator,
    *,
    entity_id: str = "e-1",
    category: EventCategory = EventCategory.AML,
    risk_level: RiskLevel = RiskLevel.LOW,
    source_service: str = "svc",
) -> AuditEvent:
    return await agg.ingest_event(
        category=category,
        event_type="test_event",
        entity_id=entity_id,
        actor="actor",
        details={},
        risk_level=risk_level,
        source_service=source_service,
    )


# ── ingest_event ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ingest_event_returns_audit_event_with_uuid_id():
    agg = _make_aggregator()
    event = await _ingest_simple(agg)
    assert isinstance(event, AuditEvent)
    import uuid

    uuid.UUID(event.id)  # raises if not valid UUID


@pytest.mark.asyncio
async def test_ingest_event_can_be_queried_back():
    agg = _make_aggregator()
    event = await _ingest_simple(agg, entity_id="entity-stored")
    results = await agg.query_events()
    ids = [e.id for e in results]
    assert event.id in ids


# ── query_events ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_query_events_no_filters_returns_all():
    agg = _make_aggregator()
    for _ in range(5):
        await _ingest_simple(agg)
    results = await agg.query_events()
    assert len(results) == 5


@pytest.mark.asyncio
async def test_query_events_filter_by_category():
    agg = _make_aggregator()
    await _ingest_simple(agg, category=EventCategory.AML)
    await _ingest_simple(agg, category=EventCategory.KYC)
    await _ingest_simple(agg, category=EventCategory.PAYMENT)
    results = await agg.query_events(category=EventCategory.AML)
    assert all(e.category == EventCategory.AML for e in results)
    assert len(results) == 1


@pytest.mark.asyncio
async def test_query_events_filter_by_entity_id():
    agg = _make_aggregator()
    await _ingest_simple(agg, entity_id="entity-A")
    await _ingest_simple(agg, entity_id="entity-B")
    results = await agg.query_events(entity_id="entity-A")
    assert len(results) == 1
    assert results[0].entity_id == "entity-A"


@pytest.mark.asyncio
async def test_query_events_filter_by_risk_level_high():
    agg = _make_aggregator()
    await _ingest_simple(agg, risk_level=RiskLevel.LOW)
    await _ingest_simple(agg, risk_level=RiskLevel.HIGH)
    await _ingest_simple(agg, risk_level=RiskLevel.CRITICAL)
    results = await agg.query_events(risk_level=RiskLevel.HIGH)
    assert len(results) == 1
    assert results[0].risk_level == RiskLevel.HIGH


@pytest.mark.asyncio
async def test_query_events_filter_by_date_range():
    store = _make_store()
    agg = AuditAggregator(store=store)

    old_event = AuditEvent(
        id="old-1",
        category=EventCategory.AUTH,
        event_type="login",
        entity_id="e",
        actor="a",
        details={},
        risk_level=RiskLevel.LOW,
        created_at=_NOW - timedelta(days=10),
        source_service="auth",
    )
    await store.ingest(old_event)
    await _ingest_simple(agg)  # recent

    from_dt = _NOW - timedelta(hours=1)
    results = await agg.query_events(from_dt=from_dt)
    assert len(results) == 1
    assert results[0].id != "old-1"


@pytest.mark.asyncio
async def test_query_events_limit_applied():
    agg = _make_aggregator()
    for _ in range(10):
        await _ingest_simple(agg)
    results = await agg.query_events(limit=5)
    assert len(results) == 5


# ── get_event_summary ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_event_summary_returns_total_key():
    agg = _make_aggregator()
    await _ingest_simple(agg)
    from_dt = _NOW - timedelta(hours=1)
    to_dt = _NOW + timedelta(hours=1)
    summary = await agg.get_event_summary(from_dt, to_dt)
    assert "total" in summary
    assert summary["total"] >= 1


@pytest.mark.asyncio
async def test_get_event_summary_by_category_key_present():
    agg = _make_aggregator()
    await _ingest_simple(agg, category=EventCategory.AML)
    from_dt = _NOW - timedelta(hours=1)
    to_dt = _NOW + timedelta(hours=1)
    summary = await agg.get_event_summary(from_dt, to_dt)
    assert "by_category" in summary
    assert "AML" in summary["by_category"]


@pytest.mark.asyncio
async def test_get_event_summary_high_risk_count_key_present():
    agg = _make_aggregator()
    await _ingest_simple(agg, risk_level=RiskLevel.CRITICAL)
    from_dt = _NOW - timedelta(hours=1)
    to_dt = _NOW + timedelta(hours=1)
    summary = await agg.get_event_summary(from_dt, to_dt)
    assert "high_risk_count" in summary
    assert summary["high_risk_count"] >= 1


@pytest.mark.asyncio
async def test_get_event_summary_empty_window_returns_zero_total():
    agg = _make_aggregator()
    await _ingest_simple(agg)
    # window in the far future — no events
    from_dt = _NOW + timedelta(days=100)
    to_dt = _NOW + timedelta(days=200)
    summary = await agg.get_event_summary(from_dt, to_dt)
    assert summary["total"] == 0


# ── get_entity_timeline ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_entity_timeline_returns_events_for_entity_only():
    agg = _make_aggregator()
    await _ingest_simple(agg, entity_id="target-entity")
    await _ingest_simple(agg, entity_id="other-entity")
    timeline = await agg.get_entity_timeline("target-entity")
    assert all(e.entity_id == "target-entity" for e in timeline)


@pytest.mark.asyncio
async def test_get_entity_timeline_limit_respected():
    agg = _make_aggregator()
    for _ in range(20):
        await _ingest_simple(agg, entity_id="big-entity")
    timeline = await agg.get_entity_timeline("big-entity", limit=5)
    assert len(timeline) == 5


# ── Multi-service / category-specific ────────────────────────────────────────


@pytest.mark.asyncio
async def test_ingest_multiple_events_from_different_services():
    agg = _make_aggregator()
    for svc in ["aml-svc", "kyc-svc", "payment-svc"]:
        await _ingest_simple(agg, source_service=svc)
    results = await agg.query_events()
    services = {e.source_service for e in results}
    assert "aml-svc" in services
    assert "kyc-svc" in services


@pytest.mark.asyncio
async def test_query_with_category_aml():
    agg = _make_aggregator()
    await _ingest_simple(agg, category=EventCategory.AML)
    await _ingest_simple(agg, category=EventCategory.KYC)
    results = await agg.query_events(category=EventCategory.AML)
    assert len(results) == 1


@pytest.mark.asyncio
async def test_query_with_category_payment():
    agg = _make_aggregator()
    await _ingest_simple(agg, category=EventCategory.PAYMENT)
    results = await agg.query_events(category=EventCategory.PAYMENT)
    assert len(results) == 1


@pytest.mark.asyncio
async def test_empty_store_query_returns_empty_list():
    agg = _make_aggregator()
    results = await agg.query_events()
    assert results == []


@pytest.mark.asyncio
async def test_get_event_summary_by_risk_level_dict():
    agg = _make_aggregator()
    await _ingest_simple(agg, risk_level=RiskLevel.HIGH)
    await _ingest_simple(agg, risk_level=RiskLevel.CRITICAL)
    from_dt = _NOW - timedelta(hours=1)
    to_dt = _NOW + timedelta(hours=1)
    summary = await agg.get_event_summary(from_dt, to_dt)
    assert "by_risk_level" in summary
    assert isinstance(summary["by_risk_level"], dict)


@pytest.mark.asyncio
async def test_ingest_10_events_query_limit_5():
    agg = _make_aggregator()
    for _ in range(10):
        await _ingest_simple(agg)
    results = await agg.query_events(limit=5)
    assert len(results) == 5
