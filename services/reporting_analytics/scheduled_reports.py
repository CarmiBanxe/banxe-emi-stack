"""
services/reporting_analytics/scheduled_reports.py
IL-RAP-01 | Phase 38 | banxe-emi-stack

Scheduled Reports — create, update, run, and manage report schedules.
I-27: Schedule updates ALWAYS return HITLProposal.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import uuid

from services.reporting_analytics.analytics_agent import HITLProposal
from services.reporting_analytics.models import (
    InMemoryScheduledReportPort,
    ReportJob,
    ScheduledReport,
    ScheduledReportPort,
    ScheduleFrequency,
)
from services.reporting_analytics.report_builder import ReportBuilder

_FREQUENCY_DELTA: dict[ScheduleFrequency, timedelta] = {
    ScheduleFrequency.DAILY: timedelta(days=1),
    ScheduleFrequency.WEEKLY: timedelta(weeks=1),
    ScheduleFrequency.MONTHLY: timedelta(days=30),
    ScheduleFrequency.QUARTERLY: timedelta(days=90),
    ScheduleFrequency.ON_DEMAND: timedelta(days=0),
}


class ScheduledReports:
    """Manages scheduled report execution."""

    def __init__(
        self,
        schedule_store: ScheduledReportPort | None = None,
        builder: ReportBuilder | None = None,
    ) -> None:
        self._store: ScheduledReportPort = schedule_store or InMemoryScheduledReportPort()
        self._builder = builder or ReportBuilder()

    def create_schedule(
        self,
        template_id: str,
        frequency: ScheduleFrequency,
        delivery: dict,
        created_by: str,
    ) -> ScheduledReport:
        """Create a new scheduled report; set next_run based on frequency."""
        now = datetime.now(UTC)
        delta = _FREQUENCY_DELTA.get(frequency, timedelta(days=1))
        next_run = now + delta if delta.total_seconds() > 0 else now + timedelta(days=1)

        schedule = ScheduledReport(
            id=str(uuid.uuid4()),
            template_id=template_id,
            frequency=frequency,
            next_run=next_run,
            last_run=None,
            delivery=delivery,
            active=True,
            created_by=created_by,
        )
        self._store.save_schedule(schedule)
        return schedule

    def update_schedule(
        self,
        schedule_id: str,
        frequency: ScheduleFrequency | None,
        delivery: dict | None,
    ) -> HITLProposal:
        """Schedule changes always require human approval (I-27)."""
        changes = {}
        if frequency is not None:
            changes["frequency"] = frequency.value
        if delivery is not None:
            changes["delivery"] = delivery
        return HITLProposal(
            action="update_schedule",
            resource_id=schedule_id,
            requires_approval_from="Analytics Manager",
            reason=f"Schedule update for {schedule_id}: {list(changes.keys())}",
            autonomy_level="L4",
        )

    def run_due_reports(self, as_of: datetime | None = None) -> list[ReportJob]:
        """Run all schedules where next_run <= as_of; update next_run."""
        cutoff = as_of or datetime.now(UTC)
        jobs: list[ReportJob] = []
        for schedule in self._store.list_active():
            if schedule.next_run <= cutoff:
                try:
                    job = self._builder.build_report(schedule.template_id, {})
                    jobs.append(job)
                except ValueError:
                    pass
                delta = _FREQUENCY_DELTA.get(schedule.frequency, timedelta(days=1))
                new_next = cutoff + (delta if delta.total_seconds() > 0 else timedelta(days=1))
                updated = ScheduledReport(
                    id=schedule.id,
                    template_id=schedule.template_id,
                    frequency=schedule.frequency,
                    next_run=new_next,
                    last_run=cutoff,
                    delivery=schedule.delivery,
                    active=schedule.active,
                    created_by=schedule.created_by,
                )
                self._store.save_schedule(updated)
        return jobs

    def get_schedule(self, schedule_id: str) -> ScheduledReport | None:
        """Return schedule by ID."""
        return self._store.get_schedule(schedule_id)

    def list_active_schedules(self) -> list[ScheduledReport]:
        """Return all active schedules."""
        return self._store.list_active()

    def deactivate_schedule(self, schedule_id: str) -> ScheduledReport:
        """Deactivate a schedule."""
        schedule = self._store.get_schedule(schedule_id)
        if schedule is None:
            raise ValueError(f"Schedule {schedule_id!r} not found")
        deactivated = ScheduledReport(
            id=schedule.id,
            template_id=schedule.template_id,
            frequency=schedule.frequency,
            next_run=schedule.next_run,
            last_run=schedule.last_run,
            delivery=schedule.delivery,
            active=False,
            created_by=schedule.created_by,
        )
        self._store.save_schedule(deactivated)
        return deactivated
