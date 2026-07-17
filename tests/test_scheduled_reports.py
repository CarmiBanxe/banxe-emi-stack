"""tests/test_scheduled_reports.py — coverage for ScheduledReports [IL-S4-WAVE3-01].

Tests only; no service code changed. ScheduledReports is fully in-memory
(default InMemoryScheduledReportPort + ReportBuilder) — nothing live to mock.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from services.reporting_analytics.analytics_agent import HITLProposal
from services.reporting_analytics.models import ScheduleFrequency
from services.reporting_analytics.scheduled_reports import ScheduledReports


class _FakeBuilder:
    """Stand-in ReportBuilder: builds for any template except the id 'bad'."""

    def build_report(self, template_id: str, parameters: dict) -> object:
        if template_id == "bad":
            raise ValueError(f"Template {template_id!r} not found")
        return object()  # a stand-in ReportJob (run_due_reports only appends it)


def test_create_schedule_sets_future_next_run_for_every_frequency() -> None:
    sr = ScheduledReports()
    for freq in ScheduleFrequency:
        schedule = sr.create_schedule("tmpl", freq, {"email": "x@y.z"}, "alice")
        assert schedule.active is True
        assert schedule.created_by == "alice"
        # even ON_DEMAND (zero delta) is pushed a day out, never in the past
        assert schedule.next_run > datetime.now(UTC)
        assert sr.get_schedule(schedule.id).id == schedule.id


def test_update_schedule_always_returns_hitl_proposal() -> None:
    sr = ScheduledReports()
    proposal = sr.update_schedule("sch-1", ScheduleFrequency.WEEKLY, {"email": "a@b.c"})
    assert isinstance(proposal, HITLProposal)
    assert proposal.action == "update_schedule"
    assert proposal.resource_id == "sch-1"
    assert proposal.autonomy_level == "L4"  # I-27
    # None arguments → empty change set, still an L4 proposal
    proposal_none = sr.update_schedule("sch-2", None, None)
    assert proposal_none.resource_id == "sch-2"


def test_run_due_reports_builds_due_and_skips_build_errors() -> None:
    sr = ScheduledReports(builder=_FakeBuilder())
    good = sr.create_schedule("good", ScheduleFrequency.DAILY, {}, "alice")
    sr.create_schedule("bad", ScheduleFrequency.DAILY, {}, "alice")  # build_report raises
    # push the cutoff past both next_runs so both are due
    jobs = sr.run_due_reports(as_of=datetime.now(UTC) + timedelta(days=2))
    assert len(jobs) == 1  # 'good' produced a job; 'bad' ValueError was swallowed
    refreshed = sr.get_schedule(good.id)
    assert refreshed.last_run is not None
    assert refreshed.next_run > datetime.now(UTC)  # next_run advanced


def test_run_due_reports_skips_not_yet_due() -> None:
    sr = ScheduledReports(builder=_FakeBuilder())
    sr.create_schedule("good", ScheduleFrequency.MONTHLY, {}, "alice")
    # cutoff before next_run → nothing runs
    assert sr.run_due_reports(as_of=datetime.now(UTC)) == []


def test_list_active_and_deactivate_schedule() -> None:
    sr = ScheduledReports()
    schedule = sr.create_schedule("tmpl", ScheduleFrequency.MONTHLY, {}, "bob")
    assert any(s.id == schedule.id for s in sr.list_active_schedules())
    deactivated = sr.deactivate_schedule(schedule.id)
    assert deactivated.active is False
    with pytest.raises(ValueError, match="not found"):
        sr.deactivate_schedule("ghost")
