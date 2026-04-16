"""
api/routers/regulatory.py — Regulatory Reporting Automation endpoints
IL-RRA-01 | Phase 14 | banxe-emi-stack

Automated regulatory report generation, validation, submission, and scheduling.

Endpoints:
  POST /v1/regulatory/reports/generate       — generate + validate a report
  POST /v1/regulatory/reports/{id}/submit    — submit validated report (L4 HITL)
  GET  /v1/regulatory/reports/audit          — query audit trail
  POST /v1/regulatory/schedules              — schedule recurring report
  DELETE /v1/regulatory/schedules/{id}       — cancel scheduled report
  GET  /v1/regulatory/schedules/{entity_id}  — list active schedules
  GET  /v1/regulatory/templates              — list supported report templates

FCA refs: SUP 16.12, SYSC 9.1.1R
I-27: submission endpoints are L4 — human MUST confirm.
"""

from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache
from typing import Any
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.regulatory_reporting.models import (
    FILING_SLA_DAYS,
    REPORT_TEMPLATES,
    InMemoryAuditTrail,
    InMemoryRegulatorGateway,
    InMemoryScheduler,
    InMemoryValidator,
    RegulatorTarget,
    ReportPeriod,
    ReportRequest,
    ReportStatus,
    ReportType,
    ScheduledReport,
    ScheduleFrequency,
)
from services.regulatory_reporting.regulatory_reporting_agent import RegulatoryReportingAgent
from services.regulatory_reporting.xml_generator import FCARegDataXMLGenerator

router = APIRouter(tags=["Regulatory Reporting"])


# ── Service factory ────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _get_agent() -> RegulatoryReportingAgent:
    """Construct agent with real (or sandbox) adapters."""
    return RegulatoryReportingAgent(
        xml_generator=FCARegDataXMLGenerator(),
        validator=InMemoryValidator(),  # swap for XSDValidator in prod
        audit_trail=InMemoryAuditTrail(),
        scheduler=InMemoryScheduler(),
        regulator_gateway=InMemoryRegulatorGateway(),
    )


# ── Request / Response models ──────────────────────────────────────────────────


class GenerateReportRequest(BaseModel):
    report_type: str = Field(..., description="e.g. FIN060, FIN071, FSA076")
    entity_id: str = Field(..., description="FCA firm reference number")
    entity_name: str
    period_start: datetime
    period_end: datetime
    actor: str = Field(..., description="User/agent submitting this request")
    template_version: str = "v1"
    financial_data: dict[str, Any] = Field(default_factory=dict)


class SubmitReportRequest(BaseModel):
    request: GenerateReportRequest
    xml_content: str
    regulator_target: str = Field(..., description="e.g. FCA_REGDATA")
    actor: str


class ScheduleRequest(BaseModel):
    report_type: str
    entity_id: str
    frequency: str = Field(..., description="MONTHLY|QUARTERLY|ANNUALLY|WEEKLY")
    template_version: str = "v1"
    actor: str


class ReportResponse(BaseModel):
    report_id: str
    report_type: str
    status: str
    validation_errors: list[str]
    generated_at: str
    submitted_at: str | None = None
    submission_ref: str | None = None
    regulator_target: str | None = None
    xml_content: str | None = None


class ScheduleResponse(BaseModel):
    schedule_id: str
    report_type: str
    entity_id: str
    frequency: str
    next_run_at: str
    is_active: bool


def _build_request(req: GenerateReportRequest) -> ReportRequest:
    try:
        report_type = ReportType(req.report_type)
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail=f"Unknown report_type: {req.report_type}"
        ) from exc
    return ReportRequest(
        report_type=report_type,
        period=ReportPeriod(start=req.period_start, end=req.period_end),
        entity_id=req.entity_id,
        entity_name=req.entity_name,
        submitter_id=req.actor,
        template_version=req.template_version,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/regulatory/reports/generate", response_model=ReportResponse)
async def generate_report(body: GenerateReportRequest) -> ReportResponse:
    """Generate and validate a regulatory report. Does NOT submit (L4 gate)."""
    agent = _get_agent()
    request = _build_request(body)
    result = await agent.generate_report(request, body.financial_data, body.actor)
    return ReportResponse(
        report_id=result.request_id,
        report_type=result.report_type.value,
        status=result.status.value,
        validation_errors=result.validation_errors,
        generated_at=result.generated_at.isoformat(),
        xml_content=result.xml_content,
    )


@router.post("/regulatory/reports/{report_id}/submit", response_model=ReportResponse)
async def submit_report(report_id: str, body: SubmitReportRequest) -> ReportResponse:
    """
    Submit a validated report to the regulator.

    I-27: L4 — caller asserts that human approval has been obtained.
    """
    agent = _get_agent()
    try:
        target = RegulatorTarget(body.regulator_target)
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail=f"Unknown regulator_target: {body.regulator_target}"
        ) from exc

    request = _build_request(body.request)
    try:
        report_type = ReportType(body.request.report_type)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Re-hydrate result from caller-supplied XML
    from services.regulatory_reporting.models import ReportResult  # noqa: PLC0415

    result = ReportResult(
        request_id=report_id,
        report_type=report_type,
        status=ReportStatus.VALIDATED,
        xml_content=body.xml_content,
        pdf_content=None,
        validation_errors=[],
        submission_ref=None,
        generated_at=datetime.now(UTC),
    )
    try:
        submitted = await agent.submit_report(request, result, target, body.actor)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Regulator gateway error: {exc}") from exc

    return ReportResponse(
        report_id=submitted.request_id,
        report_type=submitted.report_type.value,
        status=submitted.status.value,
        validation_errors=[],
        generated_at=submitted.generated_at.isoformat(),
        submitted_at=submitted.submitted_at.isoformat() if submitted.submitted_at else None,
        submission_ref=submitted.submission_ref,
        regulator_target=submitted.regulator_target.value if submitted.regulator_target else None,
    )


@router.get("/regulatory/reports/audit")
async def get_audit_log(
    report_type: str | None = None,
    entity_id: str | None = None,
    days: int = 30,
) -> dict[str, Any]:
    """Query regulatory audit trail (SYSC 9 records)."""
    agent = _get_agent()
    rtype = None
    if report_type:
        try:
            rtype = ReportType(report_type)
        except ValueError as exc:
            raise HTTPException(
                status_code=422, detail=f"Unknown report_type: {report_type}"
            ) from exc
    entries = await agent.get_audit_log(report_type=rtype, entity_id=entity_id, days=days)
    return {"count": len(entries), "entries": entries}


@router.post("/regulatory/schedules", response_model=ScheduleResponse)
async def create_schedule(body: ScheduleRequest) -> ScheduleResponse:
    """Schedule a recurring regulatory report via n8n."""
    agent = _get_agent()
    try:
        report_type = ReportType(body.report_type)
        frequency = ScheduleFrequency(body.frequency)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    schedule = ScheduledReport(
        id=str(uuid.uuid4()),
        report_type=report_type,
        entity_id=body.entity_id,
        frequency=frequency,
        next_run_at=datetime.now(UTC),
        template_version=body.template_version,
    )
    success = await agent.schedule_report(schedule, body.actor)
    if not success:
        raise HTTPException(status_code=502, detail="Failed to register schedule with n8n")

    return ScheduleResponse(
        schedule_id=schedule.id,
        report_type=schedule.report_type.value,
        entity_id=schedule.entity_id,
        frequency=schedule.frequency.value,
        next_run_at=schedule.next_run_at.isoformat(),
        is_active=schedule.is_active,
    )


@router.delete("/regulatory/schedules/{schedule_id}")
async def cancel_schedule(schedule_id: str, actor: str = "system") -> dict[str, Any]:
    """Cancel a scheduled recurring report."""
    agent = _get_agent()
    success = await agent.cancel_schedule(schedule_id, actor)
    return {"schedule_id": schedule_id, "cancelled": success}


@router.get("/regulatory/schedules/{entity_id}")
async def list_schedules(entity_id: str) -> dict[str, Any]:
    """List active scheduled reports for an entity."""

    agent = _get_agent()
    schedules = await agent._scheduler.list_active(entity_id)
    return {
        "entity_id": entity_id,
        "count": len(schedules),
        "schedules": [
            {
                "id": s.id,
                "report_type": s.report_type.value,
                "frequency": s.frequency.value,
                "next_run_at": s.next_run_at.isoformat(),
                "is_active": s.is_active,
            }
            for s in schedules
        ],
    }


@router.get("/regulatory/templates")
async def list_templates() -> dict[str, Any]:
    """List all supported regulatory report templates with SLA days."""
    templates = []
    for rtype, tmpl in REPORT_TEMPLATES.items():
        templates.append(
            {
                "report_type": rtype.value,
                "version": tmpl.version,
                "description": tmpl.description,
                "regulator": tmpl.regulator.value,
                "sla_days": FILING_SLA_DAYS.get(rtype),
                "xsd_schema": tmpl.xsd_schema,
            }
        )
    return {"count": len(templates), "templates": templates}
