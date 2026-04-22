"""
api/routers/observability.py — Observability endpoints
IL-OBS-01 | banxe-emi-stack
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.observability.observability_agent import ObservabilityAgent

logger = logging.getLogger("banxe.observability")
router = APIRouter(tags=["Observability"])

_agent = ObservabilityAgent()


class AcknowledgeRequest(BaseModel):
    alert_id: str
    officer: str


@router.get("/observability/health", summary="System health aggregate")
async def get_system_health():
    report = await _agent._health.check_all()
    return {
        "overall_status": report.overall_status.value,
        "healthy_count": report.healthy_count,
        "unhealthy_count": report.unhealthy_count,
        "services": [
            {"service": s.service, "status": s.status.value, "message": s.message}
            for s in report.services
        ],
        "checked_at": report.checked_at,
    }


@router.get("/observability/health/{service}", summary="Per-service health")
async def get_service_health(service: str):
    result = await _agent._health.check_service(service)
    return {
        "service": result.service,
        "status": result.status.value,
        "message": result.message,
        "checked_at": result.checked_at,
    }


@router.get("/observability/metrics", summary="Current metrics snapshot")
async def get_metrics():
    snap = _agent._metrics.collect()
    return {
        "test_count": snap.test_count,
        "endpoint_count": snap.endpoint_count,
        "mcp_tool_count": snap.mcp_tool_count,
        "passport_count": snap.passport_count,
        "coverage_pct": str(snap.coverage_pct),
        "collected_at": snap.collected_at,
    }


@router.get("/observability/compliance", summary="Compliance status scan")
async def get_compliance_status():
    report = _agent._compliance.scan()
    return {
        "overall_flag": report.overall_flag.value,
        "violation_count": report.violation_count,
        "warning_count": report.warning_count,
        "checks": [
            {
                "invariant_id": c.invariant_id,
                "description": c.description,
                "flag": c.flag.value,
                "detail": c.detail,
            }
            for c in report.checks
        ],
        "scanned_at": report.scanned_at,
    }


@router.post(
    "/observability/alerts/acknowledge",
    summary="Acknowledge compliance alert (I-27 HITL L4)",
    status_code=200,
)
async def acknowledge_alert(body: AcknowledgeRequest):
    ok = _agent.acknowledge_alert(alert_id=body.alert_id, officer=body.officer)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Alert {body.alert_id} not found")
    return {
        "alert_id": body.alert_id,
        "acknowledged_by": body.officer,
        "status": "acknowledged",
    }
