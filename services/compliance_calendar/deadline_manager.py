"""
services/compliance_calendar/deadline_manager.py
IL-CCD-01 | Phase 42 | banxe-emi-stack

DeadlineManager — compliance deadline lifecycle management.
I-12: SHA-256 hash for evidence on completion.
I-24: All deadline actions append to audit log.
I-27: Deadline updates require HITL approval.
Trust Zone: RED
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
import hashlib
import uuid

from services.compliance_calendar.models import (
    ComplianceDeadline,
    DeadlineStatus,
    DeadlineType,
    InMemoryDeadlineStore,
    Priority,
    RecurrencePattern,
)


@dataclass
class HITLProposal:
    action: str
    resource_id: str
    requires_approval_from: str
    reason: str
    autonomy_level: str = "L4"


class _AuditStub:
    def log(self, action: str, resource_id: str, details: dict, outcome: str) -> None:
        pass


class DeadlineManager:
    """Manages compliance deadline lifecycle with audit trail."""

    def __init__(
        self,
        deadline_store: InMemoryDeadlineStore | None = None,
        audit_port: _AuditStub | None = None,
    ) -> None:
        self._deadlines = deadline_store or InMemoryDeadlineStore()
        self._audit = audit_port or _AuditStub()

    def create_deadline(
        self,
        title: str,
        deadline_type: DeadlineType,
        priority: Priority,
        due_date: date,
        owner: str,
        description: str,
        recurrence: RecurrencePattern | None = None,
    ) -> ComplianceDeadline:
        """Create a compliance deadline with UPCOMING status; append to audit (I-24)."""
        deadline = ComplianceDeadline(
            id=str(uuid.uuid4()),
            title=title,
            deadline_type=deadline_type,
            status=DeadlineStatus.UPCOMING,
            priority=priority,
            due_date=due_date,
            owner=owner,
            description=description,
            recurrence=recurrence,
            created_at=datetime.now(UTC),
        )
        self._deadlines.save_deadline(deadline)
        self._audit.log(
            action="create_deadline",
            resource_id=deadline.id,
            details={"title": title, "type": deadline_type.value, "due_date": str(due_date)},
            outcome="CREATED",
        )
        return deadline

    def update_deadline(self, deadline_id: str, updates: dict) -> HITLProposal:
        """Compliance deadline changes require HITL (I-27)."""
        return HITLProposal(
            action="update_deadline",
            resource_id=deadline_id,
            requires_approval_from="COMPLIANCE_OFFICER",
            reason=(
                f"Deadline {deadline_id} update requires compliance officer approval "
                "per I-27 — regulatory deadlines cannot be modified without oversight."
            ),
            autonomy_level="L4",
        )

    def complete_deadline(self, deadline_id: str, evidence: str) -> ComplianceDeadline:
        """Mark deadline complete; hash evidence (I-12); append to audit (I-24)."""
        deadline = self._deadlines.get_deadline(deadline_id)
        if deadline is None:
            raise ValueError(f"Deadline not found: {deadline_id}")
        evidence_hash = hashlib.sha256(evidence.encode()).hexdigest()
        updated = ComplianceDeadline(
            id=deadline.id,
            title=deadline.title,
            deadline_type=deadline.deadline_type,
            status=DeadlineStatus.COMPLETED,
            priority=deadline.priority,
            due_date=deadline.due_date,
            owner=deadline.owner,
            description=deadline.description,
            recurrence=deadline.recurrence,
            evidence_hash=evidence_hash,
            created_at=deadline.created_at,
            completed_at=datetime.now(UTC),
        )
        self._deadlines.save_deadline(updated)
        self._audit.log(
            action="complete_deadline",
            resource_id=deadline_id,
            details={"evidence_hash": evidence_hash},
            outcome="COMPLETED",
        )
        return updated

    def miss_deadline(self, deadline_id: str) -> ComplianceDeadline:
        """Mark deadline OVERDUE; auto-escalate CRITICAL to ESCALATED; append audit (I-24)."""
        deadline = self._deadlines.get_deadline(deadline_id)
        if deadline is None:
            raise ValueError(f"Deadline not found: {deadline_id}")
        new_status = (
            DeadlineStatus.ESCALATED
            if deadline.priority == Priority.CRITICAL
            else DeadlineStatus.OVERDUE
        )
        updated = ComplianceDeadline(
            id=deadline.id,
            title=deadline.title,
            deadline_type=deadline.deadline_type,
            status=new_status,
            priority=deadline.priority,
            due_date=deadline.due_date,
            owner=deadline.owner,
            description=deadline.description,
            recurrence=deadline.recurrence,
            evidence_hash=deadline.evidence_hash,
            created_at=deadline.created_at,
            completed_at=deadline.completed_at,
        )
        self._deadlines.save_deadline(updated)
        self._audit.log(
            action="miss_deadline",
            resource_id=deadline_id,
            details={"new_status": new_status.value, "priority": deadline.priority.value},
            outcome=new_status.value,
        )
        return updated

    def list_upcoming(self, days_ahead: int = 30) -> list[ComplianceDeadline]:
        """Return UPCOMING deadlines due within days_ahead days from today."""
        today = date.today()
        cutoff = date.fromordinal(today.toordinal() + days_ahead)
        return [
            d
            for d in self._deadlines.list_all()
            if d.status == DeadlineStatus.UPCOMING and d.due_date <= cutoff
        ]

    def get_overdue(self) -> list[ComplianceDeadline]:
        """Return OVERDUE + ESCALATED deadlines."""
        return [
            d
            for d in self._deadlines.list_all()
            if d.status in (DeadlineStatus.OVERDUE, DeadlineStatus.ESCALATED)
        ]
