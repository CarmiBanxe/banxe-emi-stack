"""
services/compliance_calendar/recurrence_calculator.py
IL-CCD-01 | Phase 42 | banxe-emi-stack

RecurrenceCalculator — UK fiscal calendar and FCA reporting date calculations.
Trust Zone: RED
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta

from services.compliance_calendar.models import RecurrencePattern

UK_TAX_YEAR_START_MONTH = 4  # April
UK_TAX_YEAR_START_DAY = 6


class RecurrenceCalculator:
    """Calculates recurrence dates and UK fiscal periods."""

    def calculate_next(self, current: date, pattern: RecurrencePattern) -> date:
        """Calculate next date for a recurrence pattern."""
        if pattern == RecurrencePattern.DAILY:
            return current + timedelta(days=1)
        if pattern == RecurrencePattern.WEEKLY:
            return current + timedelta(days=7)
        if pattern == RecurrencePattern.MONTHLY:
            return self._add_months(current, 1)
        if pattern == RecurrencePattern.QUARTERLY:
            return self._add_months(current, 3)
        if pattern == RecurrencePattern.ANNUAL:
            return self._add_years(current, 1)
        raise ValueError(f"Unknown recurrence pattern: {pattern}")

    def _add_months(self, d: date, months: int) -> date:
        """Add months, clamping to last day of month on overflow."""
        month = d.month - 1 + months
        year = d.year + month // 12
        month = month % 12 + 1
        day = min(d.day, calendar.monthrange(year, month)[1])
        return date(year, month, day)

    def _add_years(self, d: date, years: int) -> date:
        """Add years, handling Feb 29 leap year edge case."""
        try:
            return d.replace(year=d.year + years)
        except ValueError:
            return d.replace(year=d.year + years, day=28)

    def generate_series(self, start: date, pattern: RecurrencePattern, count: int) -> list[date]:
        """Return list of N future dates from start."""
        dates: list[date] = []
        current = start
        for _ in range(count):
            current = self.calculate_next(current, pattern)
            dates.append(current)
        return dates

    def get_fiscal_quarters(self, year: int) -> list[tuple[date, date]]:
        """UK tax year Apr 6 – Apr 5; returns 4 quarters [(start, end), ...]."""
        q1_start = date(year, 4, 6)
        q1_end = date(year, 7, 5)
        q2_start = date(year, 7, 6)
        q2_end = date(year, 10, 5)
        q3_start = date(year, 10, 6)
        q3_end = date(year + 1, 1, 5)
        q4_start = date(year + 1, 1, 6)
        q4_end = date(year + 1, 4, 5)
        return [(q1_start, q1_end), (q2_start, q2_end), (q3_start, q3_end), (q4_start, q4_end)]

    def adjust_for_weekends(self, d: date) -> date:
        """If Saturday → Monday; if Sunday → Monday (next business day)."""
        weekday = d.weekday()
        if weekday == 5:  # Saturday
            return d + timedelta(days=2)
        if weekday == 6:  # Sunday
            return d + timedelta(days=1)
        return d

    def get_fca_reporting_dates(self, year: int) -> dict[str, date]:
        """Return FCA reporting dates for the year."""
        return {
            "FIN060_Q1": self.adjust_for_weekends(date(year, 4, 30)),
            "FIN060_Q2": self.adjust_for_weekends(date(year, 7, 31)),
            "FIN060_Q3": self.adjust_for_weekends(date(year, 10, 31)),
            "FIN060_Q4": self.adjust_for_weekends(date(year + 1, 1, 31)),
            "AML_ANNUAL": self.adjust_for_weekends(date(year, 12, 31)),
            "MLR_ANNUAL": self.adjust_for_weekends(date(year, 9, 30)),
        }
