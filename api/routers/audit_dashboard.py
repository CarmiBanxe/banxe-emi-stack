"""
api/routers/audit_dashboard.py
IL-AGD-01 | Phase 16
from api.deps import require_auth

Audit & Governance Dashboard REST endpoints.
from api.deps import require_auth

GET  /audit/events                      — query events
POST /audit/events                      — ingest event
GET  /audit/risk/score/{entity_id}      — get risk score
POST /audit/reports                     — generate report
GET  /audit/reports                     — list reports
GET  /audit/reports/{report_id}         — get report by id
GET  /audit/dashboard/metrics           — live dashboard metrics
GET  /audit/governance/status           — governance/compliance status
from api.deps import require_auth

FCA ref: SYSC 9 — record-keeping.
I-24: All audit events are append-only (never deleted).
"""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.audit_dashboard.audit_aggregator import AuditAggregator
from services.audit_dashboard.dashboard_api import DashboardService
from services.audit_dashboard.governance_reporter import GovernanceReporter
from services.audit_dashboard.models import (
    EventCategory,
    InMemoryEventStore,
    InMemoryMetricsStore,
    InMemoryReportStore,
    InMemoryRiskEngine,
    RiskLevel,
)
from services.audit_dashboard.risk_scorer import RiskScorer

router = APIRouter(tags=["audit-dashboard"])


# ── Request models ────────────────────────────────────────────────────────────


class IngestEventRequest(BaseModel):
    category: str
    event_type: str
    entity_id: str
    actor: str
    details: dict = Field(default_factory=dict)
    risk_level: str = "LOW"
    source_service: str = "unknown"


class GenerateReportRequest(BaseModel):
    title: str
    period_start: datetime
    period_end: datetime
    entity_ids: list[str] = Field(default_factory=list)
    actor: str = "system"


# ── Service factory ───────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _get_services() -> tuple[AuditAggregator, RiskScorer, GovernanceReporter, DashboardService]:
    """Build the full dashboard service graph with InMemory stubs."""
    store = InMemoryEventStore()
    report_store = InMemoryReportStore()
    risk_engine = InMemoryRiskEngine()
    metrics_store = InMemoryMetricsStore()

    aggregator = AuditAggregator(store=store)
    scorer = RiskScorer(engine=risk_engine, store=store)
    reporter = GovernanceReporter(
        aggregator=aggregator,
        scorer=scorer,
        report_store=report_store,
    )
    dashboard = DashboardService(
        aggregator=aggregator,
        scorer=scorer,
        reporter=reporter,
        metrics_store=metrics_store,
    )
    return aggregator, scorer, reporter, dashboard


# ── Helpers ───────────────────────────────────────────────────────────────────


def _parse_category(raw: str) -> EventCategory:
    try:
        return EventCategory(raw.upper())
    except ValueError:
        raise ValueError(f"Unknown category: {raw!r}. Valid: {[c.value for c in EventCategory]}")


def _parse_risk_level(raw: str) -> RiskLevel:
    try:
        return RiskLevel(raw.upper())
    except ValueError:
        raise ValueError(f"Unknown risk_level: {raw!r}. Valid: {[r.value for r in RiskLevel]}")


def _event_to_dict(event: Any) -> dict:
    return {
        "id": event.id,
        "category": event.category.value,
        "event_type": event.event_type,
        "entity_id": event.entity_id,
        "actor": event.actor,
        "details": event.details,
        "risk_level": event.risk_level.value,
        "created_at": event.created_at.isoformat(),
        "source_service": event.source_service,
    }


def _report_to_dict(report: Any) -> dict:
    return {
        "id": report.id,
        "title": report.title,
        "period_start": report.period_start.isoformat(),
        "period_end": report.period_end.isoformat(),
        "generated_at": report.generated_at.isoformat(),
        "format": report.format.value,
        "content": report.content,
        "total_events": report.total_events,
        "risk_summary": report.risk_summary,
        "compliance_score": report.compliance_score,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/audit/events")
async def query_events(
    category: str | None = None,
    entity_id: str | None = None,
    limit: int = 100,
) -> list[dict]:
    aggregator, _, _, _ = _get_services()
    try:
        cat = _parse_category(category) if category else None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    events = await aggregator.query_events(category=cat, entity_id=entity_id, limit=limit)
    return [_event_to_dict(e) for e in events]


@router.post("/audit/events")
async def ingest_event(body: IngestEventRequest) -> dict:
    aggregator, _, _, _ = _get_services()
    try:
        cat = _parse_category(body.category)
        rl = _parse_risk_level(body.risk_level)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    event = await aggregator.ingest_event(
        category=cat,
        event_type=body.event_type,
        entity_id=body.entity_id,
        actor=body.actor,
        details=body.details,
        risk_level=rl,
        source_service=body.source_service,
    )
    return _event_to_dict(event)


@router.get("/audit/risk/score/{entity_id}")
async def get_risk_score(entity_id: str) -> dict:
    _, scorer, _, _ = _get_services()
    score = await scorer.score_entity(entity_id)
    risk_level = scorer.categorise_risk(score)
    return {
        "entity_id": score.entity_id,
        "computed_at": score.computed_at.isoformat(),
        "aml_score": score.aml_score,
        "fraud_score": score.fraud_score,
        "operational_score": score.operational_score,
        "regulatory_score": score.regulatory_score,
        "overall_score": score.overall_score,
        "risk_level": risk_level.value,
        "contributing_factors": score.contributing_factors,
    }


@router.post("/audit/reports")
async def generate_report(body: GenerateReportRequest) -> dict:
    _, _, reporter, _ = _get_services()
    report = await reporter.generate_report(
        title=body.title,
        period_start=body.period_start,
        period_end=body.period_end,
        entity_ids=body.entity_ids or None,
        actor=body.actor,
    )
    return _report_to_dict(report)


@router.get("/audit/reports")
async def list_reports(limit: int = 20) -> list[dict]:
    _, _, reporter, _ = _get_services()
    reports = await reporter.list_reports(limit=limit)
    return [_report_to_dict(r) for r in reports]


@router.get("/audit/reports/{report_id}")
async def get_report(report_id: str) -> dict:
    _, _, reporter, _ = _get_services()
    report = await reporter.get_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Report {report_id!r} not found")
    return _report_to_dict(report)


@router.get("/audit/dashboard/metrics")
async def get_live_metrics() -> dict:
    _, _, _, dashboard = _get_services()
    metrics = await dashboard.get_live_metrics()
    return {
        "generated_at": metrics.generated_at.isoformat(),
        "total_events_24h": metrics.total_events_24h,
        "high_risk_events": metrics.high_risk_events,
        "compliance_score": metrics.compliance_score,
        "active_consents": metrics.active_consents,
        "pending_hitl": metrics.pending_hitl,
        "safeguarding_status": metrics.safeguarding_status,
        "risk_by_category": metrics.risk_by_category,
    }


@router.get("/audit/governance/status")
async def get_governance_status() -> dict:
    _, _, _, dashboard = _get_services()
    return await dashboard.get_governance_status()
