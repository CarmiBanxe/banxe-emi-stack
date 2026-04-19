"""
api/routers/compliance_calendar.py
IL-CCD-01 | Phase 42 | banxe-emi-stack

Compliance Calendar REST API — 9 endpoints under /v1/compliance-calendar/
Trust Zone: RED
FCA refs: FIN060, MLR 2017, PS22/9, Consumer Duty.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.compliance_calendar.calendar_reporter import CalendarReporter
from services.compliance_calendar.deadline_manager import DeadlineManager
from services.compliance_calendar.models import (
    DeadlineType,
    InMemoryDeadlineStore,
    InMemoryReminderStore,
    InMemoryTaskStore,
    Priority,
)
from services.compliance_calendar.task_tracker import TaskTracker

router = APIRouter(tags=["compliance_calendar"])

# ── Shared stores ─────────────────────────────────────────────────────────────
_deadline_store = InMemoryDeadlineStore()
_reminder_store = InMemoryReminderStore()
_task_store = InMemoryTaskStore()

_manager = DeadlineManager(deadline_store=_deadline_store)
_reporter = CalendarReporter(deadline_store=_deadline_store)
_tracker = TaskTracker(task_store=_task_store)


# ── Request / Response models ─────────────────────────────────────────────────


class CreateDeadlineRequest(BaseModel):
    title: str
    deadline_type: str
    priority: str
    due_date: str
    owner: str
    description: str = ""


class CreateTaskRequest(BaseModel):
    deadline_id: str
    title: str
    assigned_to: str
    notes: str = ""


class CompleteDeadlineRequest(BaseModel):
    evidence: str


def _deadline_to_dict(d: Any) -> dict:
    return {
        "id": d.id,
        "title": d.title,
        "deadline_type": d.deadline_type.value,
        "status": d.status.value,
        "priority": d.priority.value,
        "due_date": str(d.due_date),
        "owner": d.owner,
        "description": d.description,
        "evidence_hash": d.evidence_hash,
        "created_at": d.created_at.isoformat(),
        "completed_at": d.completed_at.isoformat() if d.completed_at else None,
    }


def _task_to_dict(t: Any) -> dict:
    return {
        "id": t.id,
        "deadline_id": t.deadline_id,
        "title": t.title,
        "assigned_to": t.assigned_to,
        "progress": t.progress,
        "status": t.status,
        "created_at": t.created_at.isoformat(),
        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/v1/compliance-calendar/deadlines/upcoming")
async def get_upcoming(days: int = 30) -> dict:
    """Get upcoming deadlines within N days."""
    deadlines = _manager.list_upcoming(days_ahead=days)
    return {"deadlines": [_deadline_to_dict(d) for d in deadlines], "days_ahead": days}


@router.get("/v1/compliance-calendar/deadlines/overdue")
async def get_overdue() -> dict:
    """Get all overdue and escalated deadlines."""
    deadlines = _manager.get_overdue()
    return {"deadlines": [_deadline_to_dict(d) for d in deadlines]}


@router.get("/v1/compliance-calendar/deadlines")
async def list_deadlines() -> dict:
    """List all compliance deadlines."""
    deadlines = _deadline_store.list_all()
    return {"deadlines": [_deadline_to_dict(d) for d in deadlines], "count": len(deadlines)}


@router.post("/v1/compliance-calendar/deadlines")
async def create_deadline(req: CreateDeadlineRequest) -> dict:
    """Create a new compliance deadline."""
    try:
        dtype = DeadlineType(req.deadline_type)
        priority = Priority(req.priority)
        due = date.fromisoformat(req.due_date)
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    deadline = _manager.create_deadline(
        title=req.title,
        deadline_type=dtype,
        priority=priority,
        due_date=due,
        owner=req.owner,
        description=req.description,
    )
    return _deadline_to_dict(deadline)


@router.get("/v1/compliance-calendar/deadlines/{deadline_id}")
async def get_deadline(deadline_id: str) -> dict:
    """Get a specific deadline by ID."""
    deadline = _deadline_store.get_deadline(deadline_id)
    if deadline is None:
        raise HTTPException(status_code=404, detail=f"Deadline not found: {deadline_id}")
    return _deadline_to_dict(deadline)


@router.post("/v1/compliance-calendar/deadlines/{deadline_id}/complete")
async def complete_deadline(deadline_id: str, req: CompleteDeadlineRequest) -> dict:
    """Mark deadline as completed with evidence hash (I-12)."""
    try:
        deadline = _manager.complete_deadline(deadline_id, req.evidence)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return _deadline_to_dict(deadline)


@router.post("/v1/compliance-calendar/tasks")
async def create_task(req: CreateTaskRequest) -> dict:
    """Create a compliance task linked to a deadline."""
    task = _tracker.create_task(
        deadline_id=req.deadline_id,
        title=req.title,
        assigned_to=req.assigned_to,
        notes=req.notes,
    )
    return _task_to_dict(task)


@router.get("/v1/compliance-calendar/tasks/{task_id}")
async def get_task(task_id: str) -> dict:
    """Get a specific task by ID."""
    task = _task_store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    return _task_to_dict(task)


@router.get("/v1/compliance-calendar/score")
async def get_compliance_score() -> dict:
    """Get current compliance score (completed / total * 100)."""
    score = _reporter.get_compliance_score()
    return {"compliance_score": str(score), "description": "Percentage of completed deadlines"}
