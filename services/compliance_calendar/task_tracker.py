"""
services/compliance_calendar/task_tracker.py
IL-CCD-01 | Phase 42 | banxe-emi-stack

TaskTracker — compliance task management linked to deadlines.
I-24: Task creation and completion append to audit log.
Trust Zone: RED
"""

from __future__ import annotations

from datetime import UTC, datetime
import uuid

from services.compliance_calendar.models import (
    ComplianceTask,
    InMemoryTaskStore,
)


class _AuditStub:
    def log(self, action: str, resource_id: str, details: dict, outcome: str) -> None:
        pass


class TaskTracker:
    """Tracks tasks linked to compliance deadlines."""

    def __init__(
        self,
        task_store: InMemoryTaskStore | None = None,
        audit_port: _AuditStub | None = None,
    ) -> None:
        self._tasks = task_store or InMemoryTaskStore()
        self._audit = audit_port or _AuditStub()

    def create_task(
        self, deadline_id: str, title: str, assigned_to: str, notes: str = ""
    ) -> ComplianceTask:
        """Create a task; status=PENDING; progress=0; append audit (I-24)."""
        task = ComplianceTask(
            id=str(uuid.uuid4()),
            deadline_id=deadline_id,
            title=title,
            assigned_to=assigned_to,
            progress=0,
            status="PENDING",
            created_at=datetime.now(UTC),
            notes=notes,
        )
        self._tasks.save_task(task)
        self._audit.log(
            action="create_task",
            resource_id=task.id,
            details={"deadline_id": deadline_id, "assigned_to": assigned_to, "title": title},
            outcome="PENDING",
        )
        return task

    def assign_task(self, task_id: str, assigned_to: str) -> ComplianceTask:
        """Reassign task to a different owner."""
        task = self._tasks.get_task(task_id)
        if task is None:
            raise ValueError(f"Task not found: {task_id}")
        updated = ComplianceTask(
            id=task.id,
            deadline_id=task.deadline_id,
            title=task.title,
            assigned_to=assigned_to,
            progress=task.progress,
            status=task.status,
            created_at=task.created_at,
            notes=task.notes,
            completed_at=task.completed_at,
        )
        self._tasks.save_task(updated)
        return updated

    def update_progress(self, task_id: str, progress: int) -> ComplianceTask:
        """Update task progress (0-100); auto-complete at 100."""
        if not 0 <= progress <= 100:
            raise ValueError(f"Progress must be 0-100, got {progress}")
        task = self._tasks.get_task(task_id)
        if task is None:
            raise ValueError(f"Task not found: {task_id}")
        status = "COMPLETED" if progress == 100 else task.status
        completed_at = datetime.now(UTC) if progress == 100 else task.completed_at
        updated = ComplianceTask(
            id=task.id,
            deadline_id=task.deadline_id,
            title=task.title,
            assigned_to=task.assigned_to,
            progress=progress,
            status=status,
            created_at=task.created_at,
            notes=task.notes,
            completed_at=completed_at,
        )
        self._tasks.save_task(updated)
        return updated

    def complete_task(self, task_id: str) -> ComplianceTask:
        """Mark task completed; append audit (I-24)."""
        task = self._tasks.get_task(task_id)
        if task is None:
            raise ValueError(f"Task not found: {task_id}")
        updated = ComplianceTask(
            id=task.id,
            deadline_id=task.deadline_id,
            title=task.title,
            assigned_to=task.assigned_to,
            progress=100,
            status="COMPLETED",
            created_at=task.created_at,
            notes=task.notes,
            completed_at=datetime.now(UTC),
        )
        self._tasks.save_task(updated)
        self._audit.log(
            action="complete_task",
            resource_id=task_id,
            details={"deadline_id": task.deadline_id},
            outcome="COMPLETED",
        )
        return updated

    def get_tasks_by_deadline(self, deadline_id: str) -> list[ComplianceTask]:
        """Return all tasks for a deadline."""
        return self._tasks.list_by_deadline(deadline_id)

    def get_workload_summary(self, assigned_to: str) -> dict:
        """Return workload breakdown for an assignee."""
        tasks = self._tasks.list_by_assignee(assigned_to)
        pending = sum(1 for t in tasks if t.status == "PENDING")
        completed = sum(1 for t in tasks if t.status == "COMPLETED")
        overdue = sum(1 for t in tasks if t.status == "OVERDUE")
        return {
            "total": len(tasks),
            "pending": pending,
            "completed": completed,
            "overdue": overdue,
        }
