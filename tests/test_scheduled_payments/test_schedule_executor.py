"""
tests/test_scheduled_payments/test_schedule_executor.py — Unit tests for ScheduleExecutor
IL-SOD-01 | Phase 32 | banxe-emi-stack
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from services.scheduled_payments.models import PaymentFrequency, PaymentType
from services.scheduled_payments.schedule_executor import ScheduleExecutor


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture()
def executor() -> ScheduleExecutor:
    return ScheduleExecutor()


# ── schedule_payment ───────────────────────────────────────────────────────────


def test_schedule_payment_returns_schedule_id(executor: ScheduleExecutor) -> None:
    result = executor.schedule_payment(PaymentType.STANDING_ORDER, "so-1", _now())
    assert result["schedule_id"] != ""


def test_schedule_payment_status_active(executor: ScheduleExecutor) -> None:
    result = executor.schedule_payment(PaymentType.STANDING_ORDER, "so-1", _now())
    assert result["status"] == "ACTIVE"


def test_schedule_payment_returns_payment_id(executor: ScheduleExecutor) -> None:
    result = executor.schedule_payment(PaymentType.DIRECT_DEBIT, "dd-1", _now())
    assert result["payment_id"] == "dd-1"


def test_schedule_payment_returns_scheduled_at(executor: ScheduleExecutor) -> None:
    scheduled = _now()
    result = executor.schedule_payment(PaymentType.STANDING_ORDER, "so-2", scheduled)
    assert result["scheduled_at"] == scheduled.isoformat()


# ── execute_due_payments ───────────────────────────────────────────────────────


def test_execute_due_payments_returns_counts(executor: ScheduleExecutor) -> None:
    result = executor.execute_due_payments(_now())
    assert "executed_count" in result
    assert "failed_count" in result


def test_execute_due_counts_past_schedules(executor: ScheduleExecutor) -> None:
    past = _now() - timedelta(hours=2)
    executor.schedule_payment(PaymentType.STANDING_ORDER, "so-exec-1", past)
    executor.schedule_payment(PaymentType.STANDING_ORDER, "so-exec-2", past)
    result = executor.execute_due_payments(_now())
    assert result["executed_count"] >= 2


def test_execute_due_skips_future_schedules(executor: ScheduleExecutor) -> None:
    future = _now() + timedelta(hours=24)
    executor.schedule_payment(PaymentType.STANDING_ORDER, "so-future", future)
    result = executor.execute_due_payments(_now())
    assert result["executed_count"] == 0


def test_execute_due_returns_total_processed(executor: ScheduleExecutor) -> None:
    result = executor.execute_due_payments(_now())
    assert result["total_processed"] == result["executed_count"] + result["failed_count"]


# ── get_upcoming_payments ──────────────────────────────────────────────────────


def test_get_upcoming_payments_empty_for_new_customer(executor: ScheduleExecutor) -> None:
    result = executor.get_upcoming_payments("nobody")
    assert result["count"] == 0


def test_get_upcoming_payments_returns_count(executor: ScheduleExecutor) -> None:
    result = executor.get_upcoming_payments("cust-1")
    assert "count" in result


def test_get_upcoming_payments_default_days_ahead(executor: ScheduleExecutor) -> None:
    result = executor.get_upcoming_payments("cust-1")
    assert result["days_ahead"] == 7


def test_get_upcoming_payments_custom_days_ahead(executor: ScheduleExecutor) -> None:
    result = executor.get_upcoming_payments("cust-1", days_ahead=14)
    assert result["days_ahead"] == 14


# ── calculate_next_date ────────────────────────────────────────────────────────


def test_calculate_next_date_daily(executor: ScheduleExecutor) -> None:
    base = _now()
    result = executor.calculate_next_date(PaymentFrequency.DAILY, base)
    assert result == base + timedelta(days=1)


def test_calculate_next_date_weekly(executor: ScheduleExecutor) -> None:
    base = _now()
    result = executor.calculate_next_date(PaymentFrequency.WEEKLY, base)
    assert result == base + timedelta(days=7)


def test_calculate_next_date_fortnightly(executor: ScheduleExecutor) -> None:
    base = _now()
    result = executor.calculate_next_date(PaymentFrequency.FORTNIGHTLY, base)
    assert result == base + timedelta(days=14)


def test_calculate_next_date_monthly(executor: ScheduleExecutor) -> None:
    base = _now()
    result = executor.calculate_next_date(PaymentFrequency.MONTHLY, base)
    assert result == base + timedelta(days=30)


def test_calculate_next_date_quarterly(executor: ScheduleExecutor) -> None:
    base = _now()
    result = executor.calculate_next_date(PaymentFrequency.QUARTERLY, base)
    assert result == base + timedelta(days=91)


def test_calculate_next_date_annual(executor: ScheduleExecutor) -> None:
    base = _now()
    result = executor.calculate_next_date(PaymentFrequency.ANNUAL, base)
    assert result == base + timedelta(days=365)
