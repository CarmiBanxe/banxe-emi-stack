"""
api/routers/audit_trail.py
IL-AES-01 | Phase 40 | banxe-emi-stack

Audit Trail REST API — 9 endpoints under /v1/audit-trail/.
I-24: Append-only. No update/delete endpoints.
I-27: Purge requires HITL proposal.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from services.audit_trail.event_replayer import EventReplayer
from services.audit_trail.event_store import EventStore
from services.audit_trail.integrity_checker import IntegrityChecker
from services.audit_trail.models import (
    AuditAction,
    EventCategory,
    EventSeverity,
    SearchQuery,
    SourceSystem,
)
from services.audit_trail.retention_enforcer import RetentionEnforcer
from services.audit_trail.search_engine import SearchEngine

router = APIRouter(tags=["audit-trail"])

_event_store = EventStore()
_replayer = EventReplayer(_event_store._events)
_searcher = SearchEngine(_event_store._events)
_integrity = IntegrityChecker(_event_store._events, _event_store._chains)
_retention = RetentionEnforcer(_event_store._events)


class LogEventRequest(BaseModel):
    category: str
    severity: str = "INFO"
    action: str
    entity_type: str
    entity_id: str
    actor_id: str
    details: dict = {}
    source: str = "API"


class SearchRequest(BaseModel):
    categories: list[str] | None = None
    severity: str | None = None
    entity_id: str | None = None
    actor_id: str | None = None
    from_ts: str | None = None
    to_ts: str | None = None
    page: int = 1
    page_size: int = 20


class SchedulePurgeRequest(BaseModel):
    category: str
    older_than_days: int


@router.post("/audit-trail/events")
def log_event(body: LogEventRequest) -> dict:
    """Append a new audit event (I-24: append-only)."""
    try:
        cat = EventCategory(body.category.upper())
        sev = EventSeverity(body.severity.upper())
        act = AuditAction(body.action.upper())
        src = SourceSystem(body.source.upper())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    event = _event_store.append(
        category=cat,
        severity=sev,
        action=act,
        entity_type=body.entity_type,
        entity_id=body.entity_id,
        actor_id=body.actor_id,
        details=body.details,
        source=src,
    )
    return {
        "event_id": event.id,
        "category": event.category.value,
        "action": event.action.value,
        "timestamp": event.timestamp.isoformat(),
        "chain_hash": event.chain_hash,
    }


@router.get("/audit-trail/events/{event_id}")
def get_event(event_id: str) -> dict:
    """Retrieve an audit event by ID."""
    event = _event_store.get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")
    return {
        "id": event.id,
        "category": event.category.value,
        "severity": event.severity.value,
        "action": event.action.value,
        "entity_type": event.entity_type,
        "entity_id": event.entity_id,
        "actor_id": event.actor_id,
        "details": event.details,
        "source": event.source.value,
        "timestamp": event.timestamp.isoformat(),
        "chain_hash": event.chain_hash,
        "prev_hash": event.prev_hash,
    }


@router.get("/audit-trail/entities/{entity_id}/events")
def list_entity_events(entity_id: str, limit: int = Query(default=50, le=500)) -> dict:
    """List audit events for an entity."""
    events = _event_store.list_by_entity(entity_id, limit)
    return {
        "entity_id": entity_id,
        "count": len(events),
        "events": [
            {
                "id": e.id,
                "category": e.category.value,
                "action": e.action.value,
                "timestamp": e.timestamp.isoformat(),
                "chain_hash": e.chain_hash,
            }
            for e in events
        ],
    }


@router.post("/audit-trail/search")
def search_events(body: SearchRequest) -> dict:
    """Search audit events with filters and pagination."""
    cats = None
    if body.categories:
        try:
            cats = [EventCategory(c.upper()) for c in body.categories]
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    sev = None
    if body.severity:
        try:
            sev = EventSeverity(body.severity.upper())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    from_ts = datetime.fromisoformat(body.from_ts) if body.from_ts else None
    to_ts = datetime.fromisoformat(body.to_ts) if body.to_ts else None
    query = SearchQuery(
        categories=cats,
        severity=sev,
        entity_id=body.entity_id,
        actor_id=body.actor_id,
        from_ts=from_ts,
        to_ts=to_ts,
        page=body.page,
        page_size=body.page_size,
    )
    result = _searcher.search(query)
    return {
        "total": result["total"],
        "page": result["page"],
        "pages": result["pages"],
        "events": [
            {
                "id": e.id,
                "category": e.category.value,
                "action": e.action.value,
                "entity_id": e.entity_id,
                "timestamp": e.timestamp.isoformat(),
            }
            for e in result["results"]
        ],
    }


@router.get("/audit-trail/entities/{entity_id}/replay")
def replay_entity(
    entity_id: str,
    from_ts: str = Query(...),
    to_ts: str = Query(...),
) -> dict:
    """Replay events for entity in time range."""
    try:
        from_dt = datetime.fromisoformat(from_ts)
        to_dt = datetime.fromisoformat(to_ts)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    events = _replayer.replay_entity(entity_id, from_dt, to_dt)
    return {
        "entity_id": entity_id,
        "from_ts": from_ts,
        "to_ts": to_ts,
        "count": len(events),
        "events": [
            {
                "id": e.id,
                "action": e.action.value,
                "timestamp": e.timestamp.isoformat(),
            }
            for e in events
        ],
    }


@router.get("/audit-trail/entities/{entity_id}/state")
def get_entity_state(entity_id: str, as_of: str = Query(...)) -> dict:
    """Reconstruct entity state as of a point in time."""
    try:
        as_of_dt = datetime.fromisoformat(as_of)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    state = _replayer.reconstruct_state(entity_id, as_of_dt)
    return {"entity_id": entity_id, "as_of": as_of, "state": state}


@router.get("/audit-trail/integrity/{source}")
def verify_integrity(source: str) -> dict:
    """Verify chain integrity for a source system."""
    try:
        src = SourceSystem(source.upper())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    report = _integrity.verify_chain(src)
    return {
        "source": src.value,
        "checked_at": report.checked_at.isoformat(),
        "total_events": report.total_events,
        "valid": report.valid,
        "tampered": report.tampered,
        "gaps": report.gaps,
        "status": report.status,
        "details": report.details,
    }


@router.get("/audit-trail/retention/rules")
def list_retention_rules() -> dict:
    """List all retention rules."""
    rules = _retention.list_rules()
    return {
        "rules": [
            {
                "policy": r.policy.value,
                "retention_days": r.retention_days,
                "category": r.category.value,
                "purge_requires_hitl": r.purge_requires_hitl,
            }
            for r in rules
        ]
    }


@router.post("/audit-trail/retention/purge")
def schedule_purge(body: SchedulePurgeRequest) -> dict:
    """Schedule purge — returns HITL proposal (I-27)."""
    try:
        cat = EventCategory(body.category.upper())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    proposal = _retention.schedule_purge(cat, body.older_than_days)
    return {
        "hitl_required": True,
        "action": proposal.action,
        "resource_id": proposal.resource_id,
        "requires_approval_from": proposal.requires_approval_from,
        "reason": proposal.reason,
        "autonomy_level": proposal.autonomy_level,
    }
