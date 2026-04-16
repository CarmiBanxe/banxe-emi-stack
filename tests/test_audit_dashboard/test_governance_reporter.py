"""
tests/test_audit_dashboard/test_governance_reporter.py
IL-AGD-01 | Phase 16

Async tests for GovernanceReporter — 15 tests.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from services.audit_dashboard.audit_aggregator import AuditAggregator
from services.audit_dashboard.governance_reporter import GovernanceReporter
from services.audit_dashboard.models import (
    GovernanceReport,
    GovernanceStatus,
    InMemoryEventStore,
    InMemoryReportStore,
    InMemoryRiskEngine,
    ReportFormat,
)
from services.audit_dashboard.risk_scorer import RiskScorer

_NOW = datetime.now(UTC)


def _make_reporter(
    store: InMemoryEventStore | None = None,
) -> tuple[GovernanceReporter, InMemoryEventStore]:
    s = store or InMemoryEventStore()
    aggregator = AuditAggregator(store=s)
    scorer = RiskScorer(engine=InMemoryRiskEngine(), store=s)
    report_store = InMemoryReportStore()
    reporter = GovernanceReporter(aggregator=aggregator, scorer=scorer, report_store=report_store)
    return reporter, s


async def _generate(
    reporter: GovernanceReporter,
    title: str = "Test Report",
    entity_ids: list[str] | None = None,
) -> GovernanceReport:
    return await reporter.generate_report(
        title=title,
        period_start=_NOW - timedelta(days=30),
        period_end=_NOW,
        entity_ids=entity_ids,
    )


# ── generate_report ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_report_returns_governance_report_with_id():
    reporter, _ = _make_reporter()
    report = await _generate(reporter)
    assert isinstance(report, GovernanceReport)
    import uuid

    uuid.UUID(report.id)  # raises if invalid UUID


@pytest.mark.asyncio
async def test_generate_report_saved_to_store():
    reporter, _ = _make_reporter()
    report = await _generate(reporter)
    fetched = await reporter.get_report(report.id)
    assert fetched is not None
    assert fetched.id == report.id


@pytest.mark.asyncio
async def test_generate_report_compliance_score_between_0_and_100():
    reporter, _ = _make_reporter()
    report = await _generate(reporter)
    assert 0.0 <= report.compliance_score <= 100.0


@pytest.mark.asyncio
async def test_generate_report_title_in_report():
    reporter, _ = _make_reporter()
    report = await _generate(reporter, title="My Board Report")
    assert report.title == "My Board Report"


@pytest.mark.asyncio
async def test_generate_report_period_start_end_preserved():
    reporter, _ = _make_reporter()
    ps = _NOW - timedelta(days=7)
    pe = _NOW
    report = await reporter.generate_report(title="Period Test", period_start=ps, period_end=pe)
    assert report.period_start == ps
    assert report.period_end == pe


# ── get_report ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_report_returns_existing_report():
    reporter, _ = _make_reporter()
    report = await _generate(reporter)
    fetched = await reporter.get_report(report.id)
    assert fetched is not None
    assert fetched.id == report.id


@pytest.mark.asyncio
async def test_get_report_missing_returns_none():
    reporter, _ = _make_reporter()
    result = await reporter.get_report("nonexistent-id")
    assert result is None


# ── list_reports ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_reports_returns_list():
    reporter, _ = _make_reporter()
    results = await reporter.list_reports()
    assert isinstance(results, list)


@pytest.mark.asyncio
async def test_list_reports_empty_initially():
    reporter, _ = _make_reporter()
    results = await reporter.list_reports()
    assert results == []


@pytest.mark.asyncio
async def test_list_reports_after_generating_3_returns_3():
    reporter, _ = _make_reporter()
    for i in range(3):
        await _generate(reporter, title=f"Report {i}")
    results = await reporter.list_reports()
    assert len(results) == 3


# ── get_compliance_status ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_compliance_status_returns_governance_status():
    reporter, _ = _make_reporter()
    status = await reporter.get_compliance_status()
    assert isinstance(status, GovernanceStatus)


@pytest.mark.asyncio
async def test_get_compliance_status_no_events_is_compliant():
    reporter, _ = _make_reporter()
    status = await reporter.get_compliance_status()
    assert status == GovernanceStatus.COMPLIANT


# ── generate_report with entity_ids ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_report_with_entity_ids():
    reporter, _ = _make_reporter()
    report = await _generate(reporter, entity_ids=["e1", "e2"])
    assert isinstance(report, GovernanceReport)
    entity_scores = report.content.get("entity_scores", [])
    assert len(entity_scores) == 2


@pytest.mark.asyncio
async def test_report_format_is_json():
    reporter, _ = _make_reporter()
    report = await _generate(reporter)
    assert report.format == ReportFormat.JSON


@pytest.mark.asyncio
async def test_total_events_in_report_is_non_negative():
    reporter, _ = _make_reporter()
    report = await _generate(reporter)
    assert report.total_events >= 0
