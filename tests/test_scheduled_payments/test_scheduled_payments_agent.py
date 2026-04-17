"""
tests/test_scheduled_payments/test_scheduled_payments_agent.py — Unit tests for ScheduledPaymentsAgent
IL-SOD-01 | Phase 32 | banxe-emi-stack
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from services.scheduled_payments.models import FailureCode, PaymentFrequency, PaymentType
from services.scheduled_payments.scheduled_payments_agent import ScheduledPaymentsAgent


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture()
def agent() -> ScheduledPaymentsAgent:
    return ScheduledPaymentsAgent()


# ── create_standing_order ──────────────────────────────────────────────────────


def test_create_so_returns_so_id(agent: ScheduledPaymentsAgent) -> None:
    result = agent.create_standing_order(
        customer_id="cust-1",
        from_account="acc-from",
        to_account="acc-to",
        amount=Decimal("100.00"),
        frequency=PaymentFrequency.MONTHLY,
        start_date=_now(),
    )
    assert result["so_id"] != ""


def test_create_so_status_active(agent: ScheduledPaymentsAgent) -> None:
    result = agent.create_standing_order(
        customer_id="cust-1",
        from_account="acc-from",
        to_account="acc-to",
        amount=Decimal("150.00"),
        frequency=PaymentFrequency.WEEKLY,
        start_date=_now(),
    )
    assert result["status"] == "ACTIVE"


def test_create_so_zero_amount_raises(agent: ScheduledPaymentsAgent) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        agent.create_standing_order(
            "c1", "fa", "ta", Decimal("0"), PaymentFrequency.MONTHLY, _now()
        )


def test_create_so_negative_amount_raises(agent: ScheduledPaymentsAgent) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        agent.create_standing_order(
            "c1", "fa", "ta", Decimal("-50"), PaymentFrequency.MONTHLY, _now()
        )


# ── create_dd_mandate ──────────────────────────────────────────────────────────


def test_create_dd_mandate_returns_mandate_id(agent: ScheduledPaymentsAgent) -> None:
    result = agent.create_dd_mandate(
        customer_id="cust-2",
        creditor_id="cred-1",
        creditor_name="Test Creditor",
        scheme_ref="REF-001",
        service_user_number="123456",
    )
    assert result["mandate_id"] != ""


def test_create_dd_mandate_status_pending(agent: ScheduledPaymentsAgent) -> None:
    result = agent.create_dd_mandate(
        customer_id="cust-2",
        creditor_id="cred-1",
        creditor_name="Test Creditor",
        scheme_ref="REF-001",
        service_user_number="123456",
    )
    assert result["status"] == "PENDING"


def test_create_dd_mandate_returns_creditor_name(agent: ScheduledPaymentsAgent) -> None:
    result = agent.create_dd_mandate(
        customer_id="cust-3",
        creditor_id="cred-2",
        creditor_name="My Gym",
        scheme_ref="GYM001",
        service_user_number="654321",
    )
    assert result["creditor_name"] == "My Gym"


# ── cancel_mandate (HITL I-27) ─────────────────────────────────────────────────


def test_cancel_mandate_always_hitl(agent: ScheduledPaymentsAgent) -> None:
    mandate = agent.create_dd_mandate("c1", "cr1", "Name", "SR1", "111")
    result = agent.cancel_mandate(mandate["mandate_id"])
    assert result["status"] == "HITL_REQUIRED"


def test_cancel_mandate_returns_mandate_id(agent: ScheduledPaymentsAgent) -> None:
    mandate = agent.create_dd_mandate("c1", "cr1", "Name", "SR1", "111")
    result = agent.cancel_mandate(mandate["mandate_id"])
    assert result["mandate_id"] == mandate["mandate_id"]


def test_cancel_mandate_not_found_raises(agent: ScheduledPaymentsAgent) -> None:
    with pytest.raises(ValueError, match="not found"):
        agent.cancel_mandate("nonexistent")


# ── get_upcoming_payments ──────────────────────────────────────────────────────


def test_get_upcoming_payments_empty_for_new_customer(agent: ScheduledPaymentsAgent) -> None:
    result = agent.get_upcoming_payments("nobody")
    assert result["count"] == 0


def test_get_upcoming_payments_returns_count(agent: ScheduledPaymentsAgent) -> None:
    result = agent.get_upcoming_payments("cust-1")
    assert "count" in result


def test_get_upcoming_payments_default_days(agent: ScheduledPaymentsAgent) -> None:
    result = agent.get_upcoming_payments("cust-1")
    assert result["days_ahead"] == 7


def test_get_upcoming_payments_custom_days(agent: ScheduledPaymentsAgent) -> None:
    result = agent.get_upcoming_payments("cust-1", days_ahead=30)
    assert result["days_ahead"] == 30


# ── get_failure_report ─────────────────────────────────────────────────────────


def test_get_failure_report_empty_for_new_customer(agent: ScheduledPaymentsAgent) -> None:
    result = agent.get_failure_report("nobody")
    assert result["count"] == 0


def test_get_failure_report_returns_customer_id(agent: ScheduledPaymentsAgent) -> None:
    result = agent.get_failure_report("cust-fail")
    assert result["customer_id"] == "cust-fail"


# ── record_payment_failure ─────────────────────────────────────────────────────


def test_record_payment_failure_returns_failure_id(agent: ScheduledPaymentsAgent) -> None:
    result = agent.record_payment_failure(
        payment_id="so-fail-1",
        payment_type=PaymentType.STANDING_ORDER,
        failure_code=FailureCode.INSUFFICIENT_FUNDS,
        failure_reason="No funds",
        customer_id="cust-1",
    )
    assert result["failure_id"] != ""


def test_record_payment_failure_returns_retry_count(agent: ScheduledPaymentsAgent) -> None:
    result = agent.record_payment_failure(
        payment_id="so-fail-2",
        payment_type=PaymentType.STANDING_ORDER,
        failure_code=FailureCode.ACCOUNT_BLOCKED,
        failure_reason="Blocked",
        customer_id="cust-2",
    )
    assert result["retry_count"] >= 1


def test_record_payment_failure_includes_notification_status(agent: ScheduledPaymentsAgent) -> None:
    result = agent.record_payment_failure(
        payment_id="so-fail-3",
        payment_type=PaymentType.DIRECT_DEBIT,
        failure_code=FailureCode.CANCELLED_BY_PAYER,
        failure_reason="Cancelled",
        customer_id="cust-3",
    )
    assert "notification_status" in result
