"""
tests/test_compliance_calendar/test_recurrence_calculator.py
IL-CCD-01 | Phase 42 | 16 tests
"""

from __future__ import annotations

from datetime import date

from services.compliance_calendar.models import RecurrencePattern
from services.compliance_calendar.recurrence_calculator import RecurrenceCalculator


def _calc() -> RecurrenceCalculator:
    return RecurrenceCalculator()


class TestCalculateNext:
    def test_daily_adds_one_day(self) -> None:
        d = date(2026, 4, 1)
        assert _calc().calculate_next(d, RecurrencePattern.DAILY) == date(2026, 4, 2)

    def test_weekly_adds_7_days(self) -> None:
        d = date(2026, 4, 1)
        assert _calc().calculate_next(d, RecurrencePattern.WEEKLY) == date(2026, 4, 8)

    def test_monthly_same_day(self) -> None:
        d = date(2026, 4, 15)
        result = _calc().calculate_next(d, RecurrencePattern.MONTHLY)
        assert result == date(2026, 5, 15)

    def test_monthly_overflow_clamps_to_last_day(self) -> None:
        d = date(2026, 1, 31)
        result = _calc().calculate_next(d, RecurrencePattern.MONTHLY)
        assert result == date(2026, 2, 28)

    def test_quarterly_adds_3_months(self) -> None:
        d = date(2026, 1, 1)
        result = _calc().calculate_next(d, RecurrencePattern.QUARTERLY)
        assert result == date(2026, 4, 1)

    def test_annual_same_month_day(self) -> None:
        d = date(2026, 4, 6)
        result = _calc().calculate_next(d, RecurrencePattern.ANNUAL)
        assert result == date(2027, 4, 6)


class TestGenerateSeries:
    def test_series_returns_n_dates(self) -> None:
        series = _calc().generate_series(date(2026, 1, 1), RecurrencePattern.MONTHLY, 3)
        assert len(series) == 3

    def test_series_dates_are_sorted(self) -> None:
        series = _calc().generate_series(date(2026, 1, 1), RecurrencePattern.WEEKLY, 5)
        assert series == sorted(series)

    def test_series_zero_returns_empty(self) -> None:
        series = _calc().generate_series(date(2026, 1, 1), RecurrencePattern.DAILY, 0)
        assert series == []


class TestFiscalQuarters:
    def test_returns_4_quarters(self) -> None:
        quarters = _calc().get_fiscal_quarters(2026)
        assert len(quarters) == 4

    def test_q1_starts_april_6(self) -> None:
        quarters = _calc().get_fiscal_quarters(2026)
        assert quarters[0][0] == date(2026, 4, 6)

    def test_q4_ends_april_5_next_year(self) -> None:
        quarters = _calc().get_fiscal_quarters(2026)
        assert quarters[3][1] == date(2027, 4, 5)


class TestAdjustForWeekends:
    def test_saturday_to_monday(self) -> None:
        saturday = date(2026, 4, 18)
        assert saturday.weekday() == 5
        result = _calc().adjust_for_weekends(saturday)
        assert result.weekday() == 0

    def test_sunday_to_monday(self) -> None:
        sunday = date(2026, 4, 19)
        assert sunday.weekday() == 6
        result = _calc().adjust_for_weekends(sunday)
        assert result.weekday() == 0

    def test_weekday_unchanged(self) -> None:
        monday = date(2026, 4, 20)
        assert _calc().adjust_for_weekends(monday) == monday


class TestFcaReportingDates:
    def test_returns_expected_keys(self) -> None:
        dates = _calc().get_fca_reporting_dates(2026)
        assert "FIN060_Q1" in dates
        assert "FIN060_Q2" in dates
        assert "FIN060_Q3" in dates
        assert "FIN060_Q4" in dates
        assert "AML_ANNUAL" in dates
        assert "MLR_ANNUAL" in dates

    def test_all_dates_are_date_objects(self) -> None:
        dates = _calc().get_fca_reporting_dates(2026)
        for key, val in dates.items():
            assert isinstance(val, date), f"{key} not a date"
