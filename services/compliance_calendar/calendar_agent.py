"""
services/compliance_calendar/calendar_agent.py
IL-CCD-01 | Phase 42 | banxe-emi-stack

CalendarAgent — orchestrates compliance calendar operations with HITL gates.
I-27: Deadline updates and board reports ALWAYS require human approval.
Trust Zone: RED
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

from services.compliance_calendar.deadline_manager import DeadlineManager
from services.compliance_calendar.models import (
    DeadlineType,
    InMemoryDeadlineStore,
    InMemoryReminderStore,
    Priority,
)
from services.compliance_calendar.reminder_engine import ReminderEngine


@dataclass
class HITLProposal:
    action: str
    resource_id: str
    requires_approval_from: str
    reason: str
    autonomy_level: str = "L4"


class CalendarAgent:
    """Autonomous compliance calendar agent with HITL gates for sensitive actions."""

    def __init__(
        self,
        deadline_store: InMemoryDeadlineStore | None = None,
        reminder_store: InMemoryReminderStore | None = None,
    ) -> None:
        self._dl_store = deadline_store or InMemoryDeadlineStore()
        self._rm_store = reminder_store or InMemoryReminderStore()
        self._manager = DeadlineManager(deadline_store=self._dl_store)
        self._reminders = ReminderEngine(
            deadline_store=self._dl_store,
            reminder_store=self._rm_store,
        )

    def process_new_deadline(
        self,
        title: str,
        deadline_type: DeadlineType,
        priority: Priority,
        due_date: date,
        owner: str,
    ) -> dict:
        """Auto-creates deadline and schedules reminders (L1)."""
        deadline = self._manager.create_deadline(
            title=title,
            deadline_type=deadline_type,
            priority=priority,
            due_date=due_date,
            owner=owner,
            description=f"Auto-created by CalendarAgent for {title}",
        )
        reminders = self._reminders.schedule_reminders(deadline.id)
        return {
            "deadline_id": deadline.id,
            "title": deadline.title,
            "status": deadline.status.value,
            "reminders_scheduled": len(reminders),
            "autonomy_level": "L1",
        }

    def process_deadline_update(self, deadline_id: str, updates: dict) -> HITLProposal:
        """Deadline updates always require HITL (I-27)."""
        return HITLProposal(
            action="update_deadline",
            resource_id=deadline_id,
            requires_approval_from="COMPLIANCE_OFFICER",
            reason=(
                f"Deadline {deadline_id} update requires compliance approval "
                "per I-27 — regulatory deadlines cannot be modified autonomously."
            ),
            autonomy_level="L4",
        )

    def process_reminder(self, deadline_id: str) -> dict:
        """Auto-sends pending reminders (L1)."""
        pending = self._reminders.get_pending_reminders(deadline_id)
        sent_count = 0
        for reminder in pending:
            self._reminders.send_reminder(reminder.id)
            sent_count += 1
        return {
            "deadline_id": deadline_id,
            "reminders_sent": sent_count,
            "autonomy_level": "L1",
        }

    def process_board_report(self, period_start: date, period_end: date) -> HITLProposal:
        """Board reports always require HITL (I-27)."""
        return HITLProposal(
            action="generate_board_report",
            resource_id=f"{period_start}_{period_end}",
            requires_approval_from="BOARD",
            reason=(
                f"Board report for {period_start} to {period_end} requires board approval per I-27."
            ),
            autonomy_level="L4",
        )

    def get_agent_status(self) -> dict:
        """Return agent operational status."""
        deadlines = self._dl_store.list_all()
        return {
            "agent": "CalendarAgent",
            "status": "ACTIVE",
            "autonomy_level": "L1",
            "hitl_gates": ["deadline_update", "board_report"],
            "total_deadlines": len(deadlines),
            "timestamp": datetime.now(UTC).isoformat(),
        }
