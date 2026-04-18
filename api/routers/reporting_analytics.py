"""
api/routers/reporting_analytics.py — Reporting & Analytics Platform REST endpoints
IL-RAP-01 | Phase 38 | banxe-emi-stack

9 REST endpoints under /v1/reports/
I-01: All amounts/scores as strings in responses (I-05).
I-27: Schedule changes return HITL proposal.
"""

from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status

from services.reporting_analytics.analytics_agent import AnalyticsAgent, HITLProposal
from services.reporting_analytics.dashboard_metrics import DashboardMetrics
from services.reporting_analytics.models import (
    DataSource,
    InMemoryReportJobPort,
    InMemoryReportTemplatePort,
    ReportFormat,
    ReportTemplate,
    ReportType,
    ScheduleFrequency,
)
from services.reporting_analytics.report_builder import ReportBuilder
from services.reporting_analytics.scheduled_reports import ScheduledReports

router = APIRouter(tags=["reports"])

# Shared in-memory stores so all singletons read from the same data
_shared_template_store = InMemoryReportTemplatePort()
_shared_job_store = InMemoryReportJobPort()


@lru_cache(maxsize=1)
def _builder() -> ReportBuilder:
    return ReportBuilder(_shared_template_store, _shared_job_store)


@lru_cache(maxsize=1)
def _agent() -> AnalyticsAgent:
    from services.reporting_analytics.export_engine import ExportEngine

    agent = AnalyticsAgent.__new__(AnalyticsAgent)
    agent._builder = _builder()
    agent._exporter = ExportEngine(_shared_job_store, _builder())
    return agent


@lru_cache(maxsize=1)
def _metrics() -> DashboardMetrics:
    return DashboardMetrics()


@lru_cache(maxsize=1)
def _scheduler() -> ScheduledReports:
    return ScheduledReports(builder=_builder())


def _agent_dep() -> AnalyticsAgent:
    return _agent()


def _builder_dep() -> ReportBuilder:
    return _builder()


def _metrics_dep() -> DashboardMetrics:
    return _metrics()


def _scheduler_dep() -> ScheduledReports:
    return _scheduler()


def _hitl_to_dict(proposal: HITLProposal) -> dict:
    return {
        "status": "HITL_REQUIRED",
        "action": proposal.action,
        "resource_id": proposal.resource_id,
        "requires_approval_from": proposal.requires_approval_from,
        "reason": proposal.reason,
        "autonomy_level": proposal.autonomy_level,
    }


def _template_to_dict(t: ReportTemplate) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "report_type": t.report_type.value,
        "format": t.format.value,
        "created_by": t.created_by,
        "created_at": t.created_at.isoformat(),
    }


# ── GET /v1/reports/templates ─────────────────────────────────────────────────


@router.get("/v1/reports/templates")
def list_templates(
    builder: Annotated[ReportBuilder, Depends(_builder_dep)],
) -> list[dict[str, Any]]:
    """List all report templates."""
    return [_template_to_dict(t) for t in builder._templates.list_templates()]


# ── POST /v1/reports/templates ────────────────────────────────────────────────


@router.post("/v1/reports/templates", status_code=status.HTTP_201_CREATED)
def create_template(
    body: Annotated[dict[str, Any], Body()],
    builder: Annotated[ReportBuilder, Depends(_builder_dep)],
) -> dict[str, Any]:
    """Create a new report template."""
    try:
        import uuid as _uuid

        template = ReportTemplate(
            id=str(_uuid.uuid4()),
            name=body["name"],
            report_type=ReportType(body["report_type"]),
            sources=[DataSource(s) for s in body.get("sources", [])],
            parameters=body.get("parameters", {}),
            format=ReportFormat(body.get("format", "JSON")),
            created_by=body.get("created_by", "api"),
            created_at=datetime.now(UTC),
        )
        builder._templates.save_template(template)
        return _template_to_dict(template)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# ── POST /v1/reports/generate ─────────────────────────────────────────────────


@router.post("/v1/reports/generate", status_code=status.HTTP_201_CREATED)
def generate_report(
    body: Annotated[dict[str, Any], Body()],
    agent: Annotated[AnalyticsAgent, Depends(_agent_dep)],
) -> dict[str, Any]:
    """Generate a report from a template."""
    try:
        return agent.process_report_request(
            body["template_id"],
            body.get("parameters", {}),
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# ── GET /v1/reports/jobs/{job_id} ─────────────────────────────────────────────


@router.get("/v1/reports/jobs/{job_id}")
def get_job(
    job_id: str,
    builder: Annotated[ReportBuilder, Depends(_builder_dep)],
) -> dict[str, Any]:
    """Get report job status."""
    job = builder.get_job_status(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return {
        "id": job.id,
        "template_id": job.template_id,
        "status": job.status,
        "output_path": job.output_path,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "error": job.error,
    }


# ── GET /v1/reports/jobs/{job_id}/export ─────────────────────────────────────


@router.get("/v1/reports/jobs/{job_id}/export")
def export_report(
    job_id: str,
    agent: Annotated[AnalyticsAgent, Depends(_agent_dep)],
    format: str = Query(default="json"),
) -> dict[str, Any]:
    """Export a report in JSON or CSV format."""
    try:
        fmt = ReportFormat(format.upper())
        return agent.process_export_request(job_id, fmt, redact_pii=True)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# ── GET /v1/reports/dashboard/kpis ───────────────────────────────────────────


@router.get("/v1/reports/dashboard/kpis")
def get_kpis(
    metrics: Annotated[DashboardMetrics, Depends(_metrics_dep)],
    period_start: str = Query(default="2026-01-01"),
    period_end: str = Query(default="2026-12-31"),
) -> list[dict[str, Any]]:
    """Get dashboard KPIs for a period."""
    try:
        start = datetime.fromisoformat(period_start).replace(tzinfo=UTC)
        end = datetime.fromisoformat(period_end).replace(tzinfo=UTC)
        kpis = metrics.get_all_kpis(start, end)
        return [
            {
                "name": k.name,
                "value": str(k.value),
                "unit": k.unit,
                "trend": k.trend,
                "sparkline": [str(v) for v in k.sparkline],
            }
            for k in kpis
        ]
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# ── POST /v1/reports/schedules ────────────────────────────────────────────────


@router.post("/v1/reports/schedules", status_code=status.HTTP_201_CREATED)
def create_schedule(
    body: Annotated[dict[str, Any], Body()],
    scheduler: Annotated[ScheduledReports, Depends(_scheduler_dep)],
) -> dict[str, Any]:
    """Create a new scheduled report."""
    try:
        schedule = scheduler.create_schedule(
            template_id=body["template_id"],
            frequency=ScheduleFrequency(body["frequency"]),
            delivery=body.get("delivery", {}),
            created_by=body.get("created_by", "api"),
        )
        return {
            "id": schedule.id,
            "template_id": schedule.template_id,
            "frequency": schedule.frequency.value,
            "next_run": schedule.next_run.isoformat(),
            "active": schedule.active,
        }
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# ── GET /v1/reports/schedules ─────────────────────────────────────────────────


@router.get("/v1/reports/schedules")
def list_schedules(
    scheduler: Annotated[ScheduledReports, Depends(_scheduler_dep)],
) -> list[dict[str, Any]]:
    """List all active schedules."""
    schedules = scheduler.list_active_schedules()
    return [
        {
            "id": s.id,
            "template_id": s.template_id,
            "frequency": s.frequency.value,
            "next_run": s.next_run.isoformat(),
            "active": s.active,
        }
        for s in schedules
    ]


# ── POST /v1/reports/schedules/{schedule_id} ─────────────────────────────────


@router.post("/v1/reports/schedules/{schedule_id}")
def update_schedule(
    schedule_id: str,
    body: Annotated[dict[str, Any], Body()],
    scheduler: Annotated[ScheduledReports, Depends(_scheduler_dep)],
) -> dict[str, Any]:
    """Update a schedule — always returns HITL proposal (I-27)."""
    try:
        frequency = ScheduleFrequency(body["frequency"]) if "frequency" in body else None
        delivery = body.get("delivery")
        proposal = scheduler.update_schedule(schedule_id, frequency, delivery)
        return _hitl_to_dict(proposal)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
