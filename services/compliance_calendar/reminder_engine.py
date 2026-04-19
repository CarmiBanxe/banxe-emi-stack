"""
services/compliance_calendar/reminder_engine.py
IL-CCD-01 | Phase 42 | banxe-emi-stack

ReminderEngine — schedule and send compliance deadline reminders.
I-24: Acknowledgements append to audit log.
Trust Zone: RED
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import uuid

from services.compliance_calendar.models import (
    DeadlineReminder,
    InMemoryDeadlineStore,
    InMemoryReminderStore,
    ReminderChannel,
)

REMINDER_SCHEDULE_DAYS = [30, 7, 1]
DEFAULT_CHANNELS = [ReminderChannel.EMAIL, ReminderChannel.TELEGRAM]


class _AuditStub:
    def log(self, action: str, resource_id: str, details: dict, outcome: str) -> None:
        pass


class ReminderEngine:
    """Schedules and dispatches compliance reminders."""

    def __init__(
        self,
        deadline_store: InMemoryDeadlineStore | None = None,
        reminder_store: InMemoryReminderStore | None = None,
        audit_port: _AuditStub | None = None,
    ) -> None:
        self._deadlines = deadline_store or InMemoryDeadlineStore()
        self._reminders = reminder_store or InMemoryReminderStore()
        self._audit = audit_port or _AuditStub()

    def schedule_reminders(
        self,
        deadline_id: str,
        channels: list[ReminderChannel] | None = None,
    ) -> list[DeadlineReminder]:
        """Create reminders at T-30d, T-7d, T-1d for each channel."""
        deadline = self._deadlines.get_deadline(deadline_id)
        if deadline is None:
            raise ValueError(f"Deadline not found: {deadline_id}")
        active_channels = channels if channels is not None else DEFAULT_CHANNELS
        created: list[DeadlineReminder] = []
        due_dt = datetime(
            deadline.due_date.year, deadline.due_date.month, deadline.due_date.day, tzinfo=UTC
        )
        for days_before in REMINDER_SCHEDULE_DAYS:
            scheduled_at = due_dt - timedelta(days=days_before)
            for channel in active_channels:
                reminder = DeadlineReminder(
                    id=str(uuid.uuid4()),
                    deadline_id=deadline_id,
                    channel=channel,
                    scheduled_at=scheduled_at,
                    message=f"Reminder T-{days_before}d: {deadline.title} due {deadline.due_date}",
                    acknowledged=False,
                    sent_at=None,
                )
                self._reminders.save_reminder(reminder)
                created.append(reminder)
        return created

    def send_reminder(self, reminder_id: str) -> DeadlineReminder:
        """Stub: set sent_at=now, status=QUEUED (no real delivery)."""
        reminder = self._reminders.get_reminder(reminder_id)
        if reminder is None:
            raise ValueError(f"Reminder not found: {reminder_id}")
        updated = DeadlineReminder(
            id=reminder.id,
            deadline_id=reminder.deadline_id,
            channel=reminder.channel,
            scheduled_at=reminder.scheduled_at,
            message=reminder.message,
            acknowledged=reminder.acknowledged,
            sent_at=datetime.now(UTC),
        )
        self._reminders.save_reminder(updated)
        return updated

    def acknowledge_reminder(self, reminder_id: str) -> DeadlineReminder:
        """Mark reminder acknowledged; append to audit (I-24)."""
        reminder = self._reminders.get_reminder(reminder_id)
        if reminder is None:
            raise ValueError(f"Reminder not found: {reminder_id}")
        updated = DeadlineReminder(
            id=reminder.id,
            deadline_id=reminder.deadline_id,
            channel=reminder.channel,
            scheduled_at=reminder.scheduled_at,
            message=reminder.message,
            acknowledged=True,
            sent_at=reminder.sent_at,
        )
        self._reminders.save_reminder(updated)
        self._audit.log(
            action="acknowledge_reminder",
            resource_id=reminder_id,
            details={"deadline_id": reminder.deadline_id, "channel": reminder.channel.value},
            outcome="ACKNOWLEDGED",
        )
        return updated

    def get_pending_reminders(self, deadline_id: str) -> list[DeadlineReminder]:
        """Return reminders where sent_at is None."""
        return self._reminders.list_pending(deadline_id)

    def configure_channels(
        self, deadline_id: str, channels: list[ReminderChannel]
    ) -> list[DeadlineReminder]:
        """Update reminder channels — creates new reminders for channels."""
        return self.schedule_reminders(deadline_id, channels)
