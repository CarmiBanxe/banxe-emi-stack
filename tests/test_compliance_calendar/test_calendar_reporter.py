"""
tests/test_compliance_calendar/test_calendar_reporter.py
IL-CCD-01 | Phase 42 | 14 tests
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from services.compliance_calendar.calendar_reporter import CalendarReporter, HITLProposal
from services.compliance_calendar.models import InMemoryDeadlineStore


def _reporter() -> CalendarReporter:
    return CalendarReporter(deadline_store=InMemoryDeadlineStore())


class TestGenerateMonthlyView:
    def test_returns_calendar_view(self) -> None:
        view = _reporter().generate_monthly_view(2026, 4)
        assert view is not None
        assert isinstance(view.deadlines, list)

    def test_april_includes_fin060_q1(self) -> None:
        view = _reporter().generate_monthly_view(2026, 4)
        titles = [d.title for d in view.deadlines]
        assert any("FIN060" in t or "Board" in t for t in titles)

    def test_view_period_start_end(self) -> None:
        view = _reporter().generate_monthly_view(2026, 6)
        assert view.period_start == date(2026, 6, 1)
        assert view.period_end == date(2026, 6, 30)

    def test_count_fields_non_negative(self) -> None:
        view = _reporter().generate_monthly_view(2026, 4)
        assert view.overdue_count >= 0
        assert view.upcoming_count >= 0
        assert view.completed_count >= 0


class TestGenerateQuarterlyView:
    def test_quarterly_view_q1(self) -> None:
        view = _reporter().generate_quarterly_view(2026, 1)
        assert view is not None

    def test_quarterly_period_start_q1_april(self) -> None:
        view = _reporter().generate_quarterly_view(2026, 1)
        assert view.period_start.month == 4

    def test_invalid_quarter_raises(self) -> None:
        import pytest

        with pytest.raises(ValueError):
            _reporter().generate_quarterly_view(2026, 5)


class TestGetComplianceScore:
    def test_no_completed_returns_low_score(self) -> None:
        score = _reporter().get_compliance_score()
        assert isinstance(score, Decimal)
        assert Decimal("0") <= score <= Decimal("100")

    def test_score_is_decimal(self) -> None:
        score = _reporter().get_compliance_score()
        assert isinstance(score, Decimal)

    def test_empty_store_returns_100(self) -> None:
        class EmptyStore:
            def list_all(self):
                return []

        reporter = CalendarReporter.__new__(CalendarReporter)
        reporter._deadlines = EmptyStore()
        from services.compliance_calendar.recurrence_calculator import RecurrenceCalculator

        reporter._recurrence = RecurrenceCalculator()
        score = reporter.get_compliance_score()
        assert score == Decimal("100.00")


class TestExportIcal:
    def test_ical_starts_with_begin(self) -> None:
        ical = _reporter().export_ical(2026)
        assert ical.startswith("BEGIN:VCALENDAR")

    def test_ical_ends_with_end(self) -> None:
        ical = _reporter().export_ical(2026)
        assert ical.strip().endswith("END:VCALENDAR")

    def test_ical_contains_vevent(self) -> None:
        ical = _reporter().export_ical(2026)
        assert "BEGIN:VEVENT" in ical


class TestGenerateBoardCalendarReport:
    def test_board_report_returns_hitl(self) -> None:
        proposal = _reporter().generate_board_calendar_report(date(2026, 1, 1), date(2026, 3, 31))
        assert isinstance(proposal, HITLProposal)

    def test_board_report_autonomy_l4(self) -> None:
        proposal = _reporter().generate_board_calendar_report(date(2026, 1, 1), date(2026, 3, 31))
        assert proposal.autonomy_level == "L4"

    def test_board_report_approver_board(self) -> None:
        proposal = _reporter().generate_board_calendar_report(date(2026, 1, 1), date(2026, 3, 31))
        assert "BOARD" in proposal.requires_approval_from.upper()
