"""
tests/test_compliance_calendar/test_reminder_engine.py
IL-CCD-01 | Phase 42 | 14 tests
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from services.compliance_calendar.deadline_manager import DeadlineManager
from services.compliance_calendar.models import (
    DeadlineType,
    InMemoryDeadlineStore,
    InMemoryReminderStore,
    Priority,
    ReminderChannel,
)
from services.compliance_calendar.reminder_engine import REMINDER_SCHEDULE_DAYS, ReminderEngine


def _setup() -> tuple[ReminderEngine, InMemoryDeadlineStore, InMemoryReminderStore, str]:
    dl_store = InMemoryDeadlineStore()
    rm_store = InMemoryReminderStore()
    manager = DeadlineManager(deadline_store=dl_store)
    dl = manager.create_deadline(
        title="Test Reminder DL",
        deadline_type=DeadlineType.FCA_RETURN,
        priority=Priority.HIGH,
        due_date=date.today() + timedelta(days=60),
        owner="CFO",
        description="Test",
    )
    engine = ReminderEngine(deadline_store=dl_store, reminder_store=rm_store)
    return engine, dl_store, rm_store, dl.id


class TestScheduleReminders:
    def test_schedule_creates_reminders(self) -> None:
        engine, _, _, dl_id = _setup()
        reminders = engine.schedule_reminders(dl_id)
        assert len(reminders) > 0

    def test_schedule_t30_t7_t1(self) -> None:
        engine, _, rm_store, dl_id = _setup()
        reminders = engine.schedule_reminders(dl_id)
        assert len(reminders) == len(REMINDER_SCHEDULE_DAYS) * 2  # 2 default channels

    def test_schedule_default_channels(self) -> None:
        engine, _, rm_store, dl_id = _setup()
        reminders = engine.schedule_reminders(dl_id)
        channels = {r.channel for r in reminders}
        assert ReminderChannel.EMAIL in channels
        assert ReminderChannel.TELEGRAM in channels

    def test_schedule_unknown_deadline_raises(self) -> None:
        engine, _, _, _ = _setup()
        with pytest.raises(ValueError):
            engine.schedule_reminders("nonexistent-id")


class TestSendReminder:
    def test_send_sets_sent_at(self) -> None:
        engine, _, _, dl_id = _setup()
        reminders = engine.schedule_reminders(dl_id)
        updated = engine.send_reminder(reminders[0].id)
        assert updated.sent_at is not None

    def test_send_unknown_raises(self) -> None:
        engine, _, _, _ = _setup()
        with pytest.raises(ValueError):
            engine.send_reminder("nonexistent-id")


class TestAcknowledgeReminder:
    def test_acknowledge_sets_flag(self) -> None:
        engine, _, _, dl_id = _setup()
        reminders = engine.schedule_reminders(dl_id)
        updated = engine.acknowledge_reminder(reminders[0].id)
        assert updated.acknowledged is True

    def test_acknowledge_unknown_raises(self) -> None:
        engine, _, _, _ = _setup()
        with pytest.raises(ValueError):
            engine.acknowledge_reminder("bad-id")


class TestGetPendingReminders:
    def test_pending_before_send(self) -> None:
        engine, _, _, dl_id = _setup()
        engine.schedule_reminders(dl_id)
        pending = engine.get_pending_reminders(dl_id)
        assert len(pending) > 0

    def test_sent_not_in_pending(self) -> None:
        engine, _, _, dl_id = _setup()
        reminders = engine.schedule_reminders(dl_id)
        engine.send_reminder(reminders[0].id)
        pending = engine.get_pending_reminders(dl_id)
        assert all(r.id != reminders[0].id for r in pending)


class TestConfigureChannels:
    def test_configure_specific_channels(self) -> None:
        engine, _, _, dl_id = _setup()
        reminders = engine.configure_channels(dl_id, [ReminderChannel.SLACK])
        channels = {r.channel for r in reminders}
        assert ReminderChannel.SLACK in channels

    def test_configure_single_channel(self) -> None:
        engine, _, _, dl_id = _setup()
        reminders = engine.configure_channels(dl_id, [ReminderChannel.WEBHOOK])
        assert len(reminders) == len(REMINDER_SCHEDULE_DAYS)
