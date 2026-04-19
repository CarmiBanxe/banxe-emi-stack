"""
services/compliance_calendar/calendar_reporter.py
IL-CCD-01 | Phase 42 | banxe-emi-stack

CalendarReporter — compliance calendar reporting with iCal export.
I-27: Board reports require HITL approval.
Trust Zone: RED
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from services.compliance_calendar.models import (
    CalendarView,
    DeadlineStatus,
    InMemoryDeadlineStore,
)
from services.compliance_calendar.recurrence_calculator import RecurrenceCalculator


@dataclass
class HITLProposal:
    action: str
    resource_id: str
    requires_approval_from: str
    reason: str
    autonomy_level: str = "L4"


class CalendarReporter:
    """Generates compliance calendar reports and views."""

    def __init__(
        self,
        deadline_store: InMemoryDeadlineStore | None = None,
    ) -> None:
        self._deadlines = deadline_store or InMemoryDeadlineStore()
        self._recurrence = RecurrenceCalculator()

    def generate_monthly_view(self, year: int, month: int) -> CalendarView:
        """Collect deadlines in month, count overdue/upcoming/completed."""
        from calendar import monthrange

        _, last_day = monthrange(year, month)
        period_start = date(year, month, 1)
        period_end = date(year, month, last_day)
        all_deadlines = self._deadlines.list_all()
        month_deadlines = [d for d in all_deadlines if period_start <= d.due_date <= period_end]
        overdue = sum(
            1
            for d in month_deadlines
            if d.status in (DeadlineStatus.OVERDUE, DeadlineStatus.ESCALATED)
        )
        upcoming = sum(1 for d in month_deadlines if d.status == DeadlineStatus.UPCOMING)
        completed = sum(1 for d in month_deadlines if d.status == DeadlineStatus.COMPLETED)
        return CalendarView(
            period_start=period_start,
            period_end=period_end,
            deadlines=month_deadlines,
            overdue_count=overdue,
            upcoming_count=upcoming,
            completed_count=completed,
        )

    def generate_quarterly_view(self, year: int, quarter: int) -> CalendarView:
        """Quarter 1–4; maps to UK fiscal quarters."""
        if not 1 <= quarter <= 4:
            raise ValueError(f"Quarter must be 1-4, got {quarter}")
        quarters = self._recurrence.get_fiscal_quarters(year)
        period_start, period_end = quarters[quarter - 1]
        all_deadlines = self._deadlines.list_all()
        q_deadlines = [d for d in all_deadlines if period_start <= d.due_date <= period_end]
        overdue = sum(
            1 for d in q_deadlines if d.status in (DeadlineStatus.OVERDUE, DeadlineStatus.ESCALATED)
        )
        upcoming = sum(1 for d in q_deadlines if d.status == DeadlineStatus.UPCOMING)
        completed = sum(1 for d in q_deadlines if d.status == DeadlineStatus.COMPLETED)
        return CalendarView(
            period_start=period_start,
            period_end=period_end,
            deadlines=q_deadlines,
            overdue_count=overdue,
            upcoming_count=upcoming,
            completed_count=completed,
        )

    def get_compliance_score(self) -> Decimal:
        """(completed / total) * 100 as Decimal, or 100.00 if no deadlines."""
        all_deadlines = self._deadlines.list_all()
        if not all_deadlines:
            return Decimal("100.00")
        completed = sum(1 for d in all_deadlines if d.status == DeadlineStatus.COMPLETED)
        score = Decimal(str(completed)) / Decimal(str(len(all_deadlines))) * Decimal("100")
        return score.quantize(Decimal("0.01"))

    def export_ical(self, year: int) -> str:
        """Stub iCal export with VEVENT per deadline."""
        all_deadlines = self._deadlines.list_all()
        year_deadlines = [d for d in all_deadlines if d.due_date.year == year]
        lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Banxe EMI//Compliance Calendar//EN"]
        for dl in year_deadlines:
            due_str = dl.due_date.strftime("%Y%m%d")
            lines.extend(
                [
                    "BEGIN:VEVENT",
                    f"UID:{dl.id}@banxe.com",
                    f"DTSTART;VALUE=DATE:{due_str}",
                    f"DTEND;VALUE=DATE:{due_str}",
                    f"SUMMARY:{dl.title}",
                    f"DESCRIPTION:{dl.description}",
                    "END:VEVENT",
                ]
            )
        lines.append("END:VCALENDAR")
        return "\n".join(lines)

    def generate_board_calendar_report(self, period_start: date, period_end: date) -> HITLProposal:
        """Board-level reports require HITL (I-27)."""
        return HITLProposal(
            action="generate_board_calendar_report",
            resource_id=f"{period_start}_{period_end}",
            requires_approval_from="BOARD",
            reason=(
                f"Board calendar report for {period_start} to {period_end} "
                "requires board approval per I-27 — AI proposes, human decides."
            ),
            autonomy_level="L4",
        )
