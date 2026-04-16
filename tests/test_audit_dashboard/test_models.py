"""
tests/test_audit_dashboard/test_models.py
IL-AGD-01 | Phase 16

Unit tests for core domain models, enums, and InMemory stubs.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from services.audit_dashboard.models import (
    AuditEvent,
    ComplianceMetric,
    DashboardMetrics,
    EventCategory,
    GovernanceReport,
    GovernanceStatus,
    InMemoryEventStore,
    InMemoryMetricsStore,
    InMemoryReportStore,
    InMemoryRiskEngine,
    ReportFormat,
    RiskLevel,
    RiskScore,
)

_NOW = datetime.now(UTC)


# ── AuditEvent ────────────────────────────────────────────────────────────────


def test_audit_event_creation():
    event = AuditEvent(
        id="evt-1",
        category=EventCategory.AML,
        event_type="threshold_breach",
        entity_id="cust-001",
        actor="system",
        details={"amount": "15000"},
        risk_level=RiskLevel.HIGH,
        created_at=_NOW,
        source_service="aml-service",
    )
    assert event.id == "evt-1"
    assert event.category == EventCategory.AML
    assert event.risk_level == RiskLevel.HIGH


def test_audit_event_is_frozen():
    event = AuditEvent(
        id="evt-2",
        category=EventCategory.KYC,
        event_type="doc_upload",
        entity_id="cust-002",
        actor="user",
        details={},
        risk_level=RiskLevel.LOW,
        created_at=_NOW,
        source_service="kyc-service",
    )
    with pytest.raises((AttributeError, TypeError)):
        event.id = "modified"  # type: ignore[misc]


# ── GovernanceReport ──────────────────────────────────────────────────────────


def test_governance_report_compliance_score_is_float():
    report = GovernanceReport(
        id="rep-1",
        title="Q1 Report",
        period_start=_NOW - timedelta(days=30),
        period_end=_NOW,
        generated_at=_NOW,
        format=ReportFormat.JSON,
        content={},
        total_events=100,
        risk_summary={"HIGH": 5},
        compliance_score=95.0,
    )
    assert isinstance(report.compliance_score, float)
    assert report.compliance_score == 95.0


# ── RiskScore ─────────────────────────────────────────────────────────────────


def test_risk_score_fields_are_float():
    score = RiskScore(
        entity_id="cust-003",
        computed_at=_NOW,
        aml_score=10.5,
        fraud_score=20.0,
        operational_score=5.0,
        regulatory_score=8.0,
        overall_score=10.875,
        contributing_factors=["test factor"],
    )
    assert isinstance(score.aml_score, float)
    assert isinstance(score.overall_score, float)
    assert not isinstance(score.aml_score, int)


def test_risk_score_contributing_factors_is_list():
    score = RiskScore(
        entity_id="cust-004",
        computed_at=_NOW,
        aml_score=0.0,
        fraud_score=0.0,
        operational_score=0.0,
        regulatory_score=0.0,
        overall_score=0.0,
        contributing_factors=["factor-a", "factor-b"],
    )
    assert isinstance(score.contributing_factors, list)
    assert len(score.contributing_factors) == 2


# ── DashboardMetrics ──────────────────────────────────────────────────────────


def test_dashboard_metrics_creation():
    m = DashboardMetrics(
        generated_at=_NOW,
        total_events_24h=50,
        high_risk_events=3,
        compliance_score=88.5,
        active_consents=10,
        pending_hitl=1,
        safeguarding_status="COMPLIANT",
        risk_by_category={"AML": 2},
    )
    assert m.total_events_24h == 50
    assert isinstance(m.compliance_score, float)


# ── ComplianceMetric ──────────────────────────────────────────────────────────


def test_compliance_metric_creation():
    cm = ComplianceMetric(
        metric_id="m-001",
        name="AML Threshold Breach Rate",
        category=EventCategory.AML,
        value=2.5,
        threshold=5.0,
        status=GovernanceStatus.COMPLIANT,
        measured_at=_NOW,
        details={"source": "automated"},
    )
    assert cm.metric_id == "m-001"
    assert cm.status == GovernanceStatus.COMPLIANT


# ── InMemoryEventStore ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_in_memory_event_store_ingest_query():
    store = InMemoryEventStore()
    event = AuditEvent(
        id="evt-10",
        category=EventCategory.PAYMENT,
        event_type="payment_initiated",
        entity_id="cust-010",
        actor="user",
        details={},
        risk_level=RiskLevel.LOW,
        created_at=_NOW,
        source_service="payment-service",
    )
    await store.ingest(event)
    results = await store.query_events()
    assert len(results) == 1
    assert results[0].id == "evt-10"


@pytest.mark.asyncio
async def test_in_memory_event_store_filter_by_category():
    store = InMemoryEventStore()
    for cat in [EventCategory.AML, EventCategory.KYC, EventCategory.PAYMENT]:
        await store.ingest(
            AuditEvent(
                id=f"evt-{cat.value}",
                category=cat,
                event_type="test",
                entity_id="e",
                actor="a",
                details={},
                risk_level=RiskLevel.LOW,
                created_at=_NOW,
                source_service="svc",
            )
        )
    aml_events = await store.query_events(category=EventCategory.AML)
    assert len(aml_events) == 1
    assert aml_events[0].category == EventCategory.AML


@pytest.mark.asyncio
async def test_in_memory_event_store_filter_by_entity_id():
    store = InMemoryEventStore()
    for i in range(3):
        await store.ingest(
            AuditEvent(
                id=f"evt-{i}",
                category=EventCategory.AUTH,
                event_type="login",
                entity_id=f"entity-{i}",
                actor="a",
                details={},
                risk_level=RiskLevel.LOW,
                created_at=_NOW,
                source_service="auth",
            )
        )
    results = await store.query_events(entity_id="entity-1")
    assert len(results) == 1
    assert results[0].entity_id == "entity-1"


@pytest.mark.asyncio
async def test_in_memory_event_store_filter_by_risk_level():
    store = InMemoryEventStore()
    for rl in [RiskLevel.LOW, RiskLevel.HIGH, RiskLevel.CRITICAL]:
        await store.ingest(
            AuditEvent(
                id=f"evt-{rl.value}",
                category=EventCategory.AML,
                event_type="check",
                entity_id="e",
                actor="a",
                details={},
                risk_level=rl,
                created_at=_NOW,
                source_service="svc",
            )
        )
    high_events = await store.query_events(risk_level=RiskLevel.HIGH)
    assert len(high_events) == 1
    assert high_events[0].risk_level == RiskLevel.HIGH


@pytest.mark.asyncio
async def test_in_memory_event_store_filter_by_date_range():
    store = InMemoryEventStore()
    old = _NOW - timedelta(days=10)
    recent = _NOW - timedelta(hours=1)
    for ts in [old, recent]:
        await store.ingest(
            AuditEvent(
                id=str(ts),
                category=EventCategory.LEDGER,
                event_type="tx",
                entity_id="e",
                actor="a",
                details={},
                risk_level=RiskLevel.LOW,
                created_at=ts,
                source_service="ledger",
            )
        )
    from_dt = _NOW - timedelta(hours=2)
    results = await store.query_events(from_dt=from_dt)
    assert len(results) == 1


# ── InMemoryReportStore ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_in_memory_report_store_save_get_list():
    store = InMemoryReportStore()
    report = GovernanceReport(
        id="rep-100",
        title="Test",
        period_start=_NOW,
        period_end=_NOW,
        generated_at=_NOW,
        format=ReportFormat.JSON,
        content={},
        total_events=0,
        risk_summary={},
        compliance_score=100.0,
    )
    await store.save_report(report)
    fetched = await store.get_report("rep-100")
    assert fetched is not None
    assert fetched.id == "rep-100"
    all_reports = await store.list_reports()
    assert len(all_reports) == 1


# ── InMemoryRiskEngine ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_in_memory_risk_engine_returns_risk_score():
    engine = InMemoryRiskEngine()
    score = await engine.compute_score("entity-99", [])
    assert isinstance(score, RiskScore)
    assert score.entity_id == "entity-99"
    assert 0.0 <= score.overall_score <= 100.0


# ── InMemoryMetricsStore ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_in_memory_metrics_store_returns_dashboard_metrics():
    store = InMemoryMetricsStore()
    m = await store.get_dashboard_metrics()
    assert isinstance(m, DashboardMetrics)
    assert m.total_events_24h >= 0


# ── Enum sanity ───────────────────────────────────────────────────────────────


def test_event_category_enum_values():
    categories = [c.value for c in EventCategory]
    assert "AML" in categories
    assert "KYC" in categories
    assert "PAYMENT" in categories
    assert "REGULATORY" in categories


def test_governance_status_enum():
    assert GovernanceStatus.COMPLIANT.value == "COMPLIANT"
    assert GovernanceStatus.NON_COMPLIANT.value == "NON_COMPLIANT"


def test_risk_level_ordering():
    levels = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]
    assert levels[0] == RiskLevel.LOW
    assert levels[-1] == RiskLevel.CRITICAL
    assert levels.index(RiskLevel.LOW) < levels.index(RiskLevel.HIGH)
