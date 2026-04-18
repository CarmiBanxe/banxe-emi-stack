"""
tests/test_reporting_analytics/test_scheduled_reports.py
IL-RAP-01 | Phase 38 | banxe-emi-stack — 16 tests
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from services.reporting_analytics.analytics_agent import HITLProposal
from services.reporting_analytics.models import (
    InMemoryReportTemplatePort,
    InMemoryScheduledReportPort,
    ScheduleFrequency,
)
from services.reporting_analytics.report_builder import ReportBuilder
from services.reporting_analytics.scheduled_reports import ScheduledReports


def _scheduler() -> tuple[ScheduledReports, str]:
    tstore = InMemoryReportTemplatePort()
    template_id = tstore.list_templates()[0].id
    sstore = InMemoryScheduledReportPort()
    from services.reporting_analytics.models import InMemoryReportJobPort

    jstore = InMemoryReportJobPort()
    builder = ReportBuilder(tstore, jstore)
    scheduler = ScheduledReports(sstore, builder)
    return scheduler, template_id


class TestCreateSchedule:
    def test_returns_schedule(self) -> None:
        scheduler, tid = _scheduler()
        s = scheduler.create_schedule(tid, ScheduleFrequency.DAILY, {}, "test-user")
        assert s.template_id == tid

    def test_is_active(self) -> None:
        scheduler, tid = _scheduler()
        s = scheduler.create_schedule(tid, ScheduleFrequency.WEEKLY, {}, "user")
        assert s.active is True

    def test_next_run_in_future(self) -> None:
        scheduler, tid = _scheduler()
        s = scheduler.create_schedule(tid, ScheduleFrequency.DAILY, {}, "user")
        assert s.next_run > datetime.now(UTC)

    def test_frequency_stored(self) -> None:
        scheduler, tid = _scheduler()
        s = scheduler.create_schedule(tid, ScheduleFrequency.MONTHLY, {}, "user")
        assert s.frequency == ScheduleFrequency.MONTHLY

    def test_created_by_stored(self) -> None:
        scheduler, tid = _scheduler()
        s = scheduler.create_schedule(tid, ScheduleFrequency.DAILY, {}, "alice")
        assert s.created_by == "alice"


class TestUpdateSchedule:
    def test_always_returns_hitl(self) -> None:
        scheduler, tid = _scheduler()
        s = scheduler.create_schedule(tid, ScheduleFrequency.DAILY, {}, "user")
        result = scheduler.update_schedule(s.id, ScheduleFrequency.WEEKLY, None)
        assert isinstance(result, HITLProposal)

    def test_autonomy_level_l4(self) -> None:
        scheduler, tid = _scheduler()
        s = scheduler.create_schedule(tid, ScheduleFrequency.DAILY, {}, "user")
        result = scheduler.update_schedule(s.id, None, {"email": "test@test.com"})
        assert result.autonomy_level == "L4"

    def test_requires_analytics_manager(self) -> None:
        scheduler, tid = _scheduler()
        s = scheduler.create_schedule(tid, ScheduleFrequency.DAILY, {}, "user")
        result = scheduler.update_schedule(s.id, ScheduleFrequency.MONTHLY, None)
        assert "Analytics Manager" in result.requires_approval_from


class TestRunDueReports:
    def test_runs_overdue_schedule(self) -> None:
        scheduler, tid = _scheduler()
        # Create a schedule with next_run in the past
        sstore = scheduler._store
        import uuid

        from services.reporting_analytics.models import ScheduledReport

        past_run = datetime.now(UTC) - timedelta(hours=2)
        s = ScheduledReport(
            id=str(uuid.uuid4()),
            template_id=tid,
            frequency=ScheduleFrequency.DAILY,
            next_run=past_run,
            last_run=None,
            delivery={},
            active=True,
            created_by="system",
        )
        sstore.save_schedule(s)
        jobs = scheduler.run_due_reports(datetime.now(UTC))
        assert len(jobs) >= 1

    def test_does_not_run_future_schedule(self) -> None:
        scheduler, tid = _scheduler()
        # All schedules have future next_run
        scheduler.create_schedule(tid, ScheduleFrequency.DAILY, {}, "user")
        jobs = scheduler.run_due_reports(datetime.now(UTC))
        assert jobs == []


class TestListActive:
    def test_returns_active_schedules(self) -> None:
        scheduler, tid = _scheduler()
        scheduler.create_schedule(tid, ScheduleFrequency.DAILY, {}, "user")
        schedules = scheduler.list_active_schedules()
        assert len(schedules) >= 1

    def test_no_deactivated_in_list(self) -> None:
        scheduler, tid = _scheduler()
        s = scheduler.create_schedule(tid, ScheduleFrequency.DAILY, {}, "user")
        scheduler.deactivate_schedule(s.id)
        active = scheduler.list_active_schedules()
        assert all(s2.active for s2 in active)


class TestDeactivateSchedule:
    def test_returns_inactive_schedule(self) -> None:
        scheduler, tid = _scheduler()
        s = scheduler.create_schedule(tid, ScheduleFrequency.DAILY, {}, "user")
        deactivated = scheduler.deactivate_schedule(s.id)
        assert deactivated.active is False

    def test_unknown_id_raises(self) -> None:
        scheduler, _ = _scheduler()
        with pytest.raises(ValueError, match="not found"):
            scheduler.deactivate_schedule("no-such-id")
