from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.sanctions_screening.alert_handler import AlertHandler
from services.sanctions_screening.compliance_reporter import ComplianceReporter
from services.sanctions_screening.list_manager import ListManager
from services.sanctions_screening.models import (
    AlertStatus,
    EntityType,
    InMemoryAlertStore,
    InMemoryHitStore,
    InMemoryListStore,
    InMemoryScreeningStore,
)
from services.sanctions_screening.sanctions_agent import SanctionsAgent
from services.sanctions_screening.screening_engine import ScreeningEngine

router = APIRouter()

# Singleton stores
_screening_store = InMemoryScreeningStore()
_list_store = InMemoryListStore()
_alert_store = InMemoryAlertStore()
_hit_store = InMemoryHitStore()

_engine = ScreeningEngine(_screening_store, _list_store, _hit_store)
_alert_handler = AlertHandler(_alert_store, _hit_store)
_reporter = ComplianceReporter(_screening_store, _alert_store)
_list_manager = ListManager(_list_store)
_agent = SanctionsAgent(_engine, _alert_handler)


class ScreenEntityRequest(BaseModel):
    entity_name: str
    entity_type: str = "individual"
    nationality: str
    date_of_birth: str = ""


class ScreenTransactionRequest(BaseModel):
    counterparty_name: str
    amount_gbp: str
    nationality: str


class EscalateRequest(BaseModel):
    escalation_reason: str
    escalated_by: str = "compliance_officer"


class ResolveRequest(BaseModel):
    is_true_positive: bool
    resolved_by: str = "compliance_officer"
    notes: str = ""


@router.post("/screen/entity")
def screen_entity(body: ScreenEntityRequest) -> dict:
    try:
        etype = EntityType(body.entity_type)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid entity_type: {body.entity_type}")
    dob = body.date_of_birth or None
    report = _engine.screen_entity(body.entity_name, etype, body.nationality, dob)
    return {
        "report_id": report.report_id,
        "request_id": report.request_id,
        "result": report.result,
        "hits": len(report.hits),
        "notes": report.notes,
        "screened_at": report.screened_at,
    }


@router.post("/screen/transaction")
def screen_transaction(body: ScreenTransactionRequest) -> dict:
    try:
        amount = Decimal(body.amount_gbp)
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid amount_gbp")
    report = _engine.screen_transaction(body.counterparty_name, amount, body.nationality)
    return {
        "report_id": report.report_id,
        "request_id": report.request_id,
        "result": report.result,
        "notes": report.notes,
        "screened_at": report.screened_at,
    }


@router.get("/requests/{request_id}")
def get_screening_request(request_id: str) -> dict:
    req = _screening_store.get_request(request_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Screening request not found")
    return {
        "request_id": req.request_id,
        "entity_name": req.entity_name,
        "nationality": req.nationality,
        "requested_at": req.requested_at,
    }


@router.get("/reports/{request_id}")
def get_screening_report(request_id: str) -> dict:
    report = _screening_store.get_report(request_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Screening report not found")
    return {
        "report_id": report.report_id,
        "request_id": report.request_id,
        "result": report.result,
        "hits": len(report.hits),
        "notes": report.notes,
        "screened_at": report.screened_at,
    }


@router.get("/alerts")
def list_alerts(status: str = "open") -> dict:
    try:
        st = AlertStatus(status)
    except ValueError:
        st = AlertStatus.OPEN
    alerts = _alert_store.list_by_status(st)
    return {
        "alerts": [
            {"alert_id": a.alert_id, "status": a.status, "created_at": a.created_at} for a in alerts
        ]
    }


@router.post("/alerts/{alert_id}/escalate")
def escalate_alert(alert_id: str, body: EscalateRequest) -> dict:
    proposal = _alert_handler.escalate_alert(alert_id, body.escalation_reason, body.escalated_by)
    return {
        "hitl_required": True,
        "action": proposal.action,
        "requires_approval_from": proposal.requires_approval_from,
        "reason": proposal.reason,
    }


@router.post("/alerts/{alert_id}/resolve")
def resolve_alert(alert_id: str, body: ResolveRequest) -> dict:
    try:
        alert = _alert_handler.resolve_alert(
            alert_id, body.is_true_positive, body.resolved_by, body.notes
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"alert_id": alert.alert_id, "status": alert.status, "resolved_at": alert.resolved_at}


@router.get("/lists")
def list_sanctions_lists() -> dict:
    lists = _list_manager.get_active_lists()
    return {
        "lists": [
            {
                "list_id": lst.list_id,
                "source": lst.source,
                "version": lst.version,
                "entry_count": lst.entry_count,
            }
            for lst in lists
        ]
    }


@router.get("/stats")
def get_screening_stats(period: str = "daily") -> dict:
    return _reporter.get_screening_stats(period)
