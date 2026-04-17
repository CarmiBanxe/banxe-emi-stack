"""
tests/test_scheduled_payments/test_models.py — Unit tests for scheduled payments domain models
IL-SOD-01 | Phase 32 | banxe-emi-stack
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import uuid

import pytest

from services.scheduled_payments.models import (
    DDMandate,
    DDStatus,
    FailureCode,
    FailureRecord,
    InMemoryDDMandateStore,
    InMemoryFailureRecordStore,
    InMemoryPaymentScheduleStore,
    InMemoryStandingOrderStore,
    PaymentFrequency,
    PaymentSchedule,
    PaymentType,
    ScheduleStatus,
    StandingOrder,
)


def _now() -> datetime:
    return datetime.now(UTC)


# ── Enum tests ─────────────────────────────────────────────────────────────────


def test_payment_frequency_values() -> None:
    assert PaymentFrequency.DAILY.value == "DAILY"
    assert PaymentFrequency.WEEKLY.value == "WEEKLY"
    assert PaymentFrequency.FORTNIGHTLY.value == "FORTNIGHTLY"
    assert PaymentFrequency.MONTHLY.value == "MONTHLY"
    assert PaymentFrequency.QUARTERLY.value == "QUARTERLY"
    assert PaymentFrequency.ANNUAL.value == "ANNUAL"


def test_schedule_status_values() -> None:
    assert ScheduleStatus.PENDING_AUTHORISATION.value == "PENDING_AUTHORISATION"
    assert ScheduleStatus.ACTIVE.value == "ACTIVE"
    assert ScheduleStatus.PAUSED.value == "PAUSED"
    assert ScheduleStatus.CANCELLED.value == "CANCELLED"
    assert ScheduleStatus.COMPLETED.value == "COMPLETED"


def test_dd_status_values() -> None:
    assert DDStatus.PENDING.value == "PENDING"
    assert DDStatus.AUTHORISED.value == "AUTHORISED"
    assert DDStatus.ACTIVE.value == "ACTIVE"
    assert DDStatus.SUSPENDED.value == "SUSPENDED"
    assert DDStatus.CANCELLED.value == "CANCELLED"


def test_failure_code_values() -> None:
    assert FailureCode.INSUFFICIENT_FUNDS.value == "INSUFFICIENT_FUNDS"
    assert FailureCode.ACCOUNT_CLOSED.value == "ACCOUNT_CLOSED"
    assert FailureCode.ACCOUNT_BLOCKED.value == "ACCOUNT_BLOCKED"
    assert FailureCode.INVALID_ACCOUNT.value == "INVALID_ACCOUNT"
    assert FailureCode.CANCELLED_BY_PAYER.value == "CANCELLED_BY_PAYER"


def test_payment_type_values() -> None:
    assert PaymentType.STANDING_ORDER.value == "STANDING_ORDER"
    assert PaymentType.DIRECT_DEBIT.value == "DIRECT_DEBIT"


# ── StandingOrder frozen dataclass ─────────────────────────────────────────────


def test_standing_order_creation() -> None:
    so = StandingOrder(
        so_id=str(uuid.uuid4()),
        customer_id="cust-1",
        from_account="acc-from",
        to_account="acc-to",
        amount=Decimal("100.00"),
        frequency=PaymentFrequency.MONTHLY,
        start_date=_now(),
        next_execution_date=_now(),
        status=ScheduleStatus.ACTIVE,
        reference="REF001",
        created_at=_now(),
    )
    assert so.amount == Decimal("100.00")
    assert so.end_date is None


def test_standing_order_frozen() -> None:
    so = StandingOrder(
        so_id="so-1",
        customer_id="c1",
        from_account="fa",
        to_account="ta",
        amount=Decimal("50.00"),
        frequency=PaymentFrequency.WEEKLY,
        start_date=_now(),
        next_execution_date=_now(),
        status=ScheduleStatus.ACTIVE,
        reference="",
        created_at=_now(),
    )
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        so.amount = Decimal("999.00")  # type: ignore[misc]


# ── DDMandate frozen dataclass ─────────────────────────────────────────────────


def test_dd_mandate_creation() -> None:
    m = DDMandate(
        mandate_id=str(uuid.uuid4()),
        customer_id="cust-2",
        creditor_id="cred-1",
        creditor_name="Test Creditor",
        scheme_ref="REF-001",
        service_user_number="123456",
        status=DDStatus.PENDING,
        created_at=_now(),
    )
    assert m.status == DDStatus.PENDING
    assert m.authorised_at is None


def test_dd_mandate_frozen() -> None:
    m = DDMandate(
        mandate_id="m-1",
        customer_id="c1",
        creditor_id="cr1",
        creditor_name="Test",
        scheme_ref="SR1",
        service_user_number="111",
        status=DDStatus.PENDING,
        created_at=_now(),
    )
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        m.status = DDStatus.ACTIVE  # type: ignore[misc]


# ── PaymentSchedule frozen dataclass ──────────────────────────────────────────


def test_payment_schedule_creation() -> None:
    s = PaymentSchedule(
        schedule_id=str(uuid.uuid4()),
        payment_type=PaymentType.STANDING_ORDER,
        payment_id="so-1",
        scheduled_at=_now(),
        status=ScheduleStatus.ACTIVE,
        created_at=_now(),
    )
    assert s.executed_at is None


# ── FailureRecord frozen dataclass ─────────────────────────────────────────────


def test_failure_record_creation() -> None:
    r = FailureRecord(
        failure_id=str(uuid.uuid4()),
        payment_id="so-1",
        payment_type=PaymentType.STANDING_ORDER,
        failure_code=FailureCode.INSUFFICIENT_FUNDS,
        failure_reason="Insufficient funds in account",
        failed_at=_now(),
        customer_id="cust-1",
        retry_count=0,
    )
    assert r.retry_count == 0
    assert r.next_retry_at is None


# ── InMemoryStandingOrderStore ─────────────────────────────────────────────────


def test_so_store_save_and_get() -> None:
    store = InMemoryStandingOrderStore()
    so = StandingOrder(
        so_id="so-test",
        customer_id="c1",
        from_account="fa",
        to_account="ta",
        amount=Decimal("100.00"),
        frequency=PaymentFrequency.MONTHLY,
        start_date=_now(),
        next_execution_date=_now(),
        status=ScheduleStatus.ACTIVE,
        reference="",
        created_at=_now(),
    )
    store.save(so)
    assert store.get("so-test") is not None


def test_so_store_update() -> None:
    store = InMemoryStandingOrderStore()
    so = StandingOrder(
        so_id="so-upd",
        customer_id="c2",
        from_account="fa",
        to_account="ta",
        amount=Decimal("200.00"),
        frequency=PaymentFrequency.WEEKLY,
        start_date=_now(),
        next_execution_date=_now(),
        status=ScheduleStatus.ACTIVE,
        reference="",
        created_at=_now(),
    )
    store.save(so)
    updated = dataclasses.replace(so, status=ScheduleStatus.PAUSED)
    store.update(updated)
    assert store.get("so-upd").status == ScheduleStatus.PAUSED


def test_so_store_list_by_customer() -> None:
    store = InMemoryStandingOrderStore()
    so = StandingOrder(
        so_id="so-list",
        customer_id="cust-list",
        from_account="fa",
        to_account="ta",
        amount=Decimal("50.00"),
        frequency=PaymentFrequency.DAILY,
        start_date=_now(),
        next_execution_date=_now(),
        status=ScheduleStatus.ACTIVE,
        reference="",
        created_at=_now(),
    )
    store.save(so)
    assert len(store.list_by_customer("cust-list")) == 1
    assert len(store.list_by_customer("nobody")) == 0


# ── InMemoryDDMandateStore ─────────────────────────────────────────────────────


def test_mandate_store_save_and_get() -> None:
    store = InMemoryDDMandateStore()
    m = DDMandate(
        mandate_id="m-test",
        customer_id="c1",
        creditor_id="cr1",
        creditor_name="Test",
        scheme_ref="SR1",
        service_user_number="111",
        status=DDStatus.PENDING,
        created_at=_now(),
    )
    store.save(m)
    assert store.get("m-test") is not None


def test_mandate_store_list_by_customer() -> None:
    store = InMemoryDDMandateStore()
    m = DDMandate(
        mandate_id="m-list",
        customer_id="cust-m",
        creditor_id="cr1",
        creditor_name="Test",
        scheme_ref="SR1",
        service_user_number="111",
        status=DDStatus.PENDING,
        created_at=_now(),
    )
    store.save(m)
    assert len(store.list_by_customer("cust-m")) == 1
    assert len(store.list_by_customer("nobody")) == 0


# ── InMemoryPaymentScheduleStore ──────────────────────────────────────────────


def test_schedule_store_list_due() -> None:
    store = InMemoryPaymentScheduleStore()
    now = _now()
    past = PaymentSchedule(
        schedule_id="s-past",
        payment_type=PaymentType.STANDING_ORDER,
        payment_id="so-1",
        scheduled_at=now - timedelta(hours=1),
        status=ScheduleStatus.ACTIVE,
        created_at=now,
    )
    future = PaymentSchedule(
        schedule_id="s-future",
        payment_type=PaymentType.STANDING_ORDER,
        payment_id="so-2",
        scheduled_at=now + timedelta(hours=1),
        status=ScheduleStatus.ACTIVE,
        created_at=now,
    )
    store.save(past)
    store.save(future)
    due = store.list_due(now)
    assert len(due) == 1
    assert due[0].schedule_id == "s-past"


def test_schedule_store_list_due_excludes_cancelled() -> None:
    store = InMemoryPaymentScheduleStore()
    now = _now()
    cancelled = PaymentSchedule(
        schedule_id="s-cancelled",
        payment_type=PaymentType.STANDING_ORDER,
        payment_id="so-3",
        scheduled_at=now - timedelta(hours=1),
        status=ScheduleStatus.CANCELLED,
        created_at=now,
    )
    store.save(cancelled)
    assert len(store.list_due(now)) == 0


# ── InMemoryFailureRecordStore (append-only I-24) ──────────────────────────────


def test_failure_store_append_only() -> None:
    store = InMemoryFailureRecordStore()
    r1 = FailureRecord(
        failure_id="f-1",
        payment_id="so-1",
        payment_type=PaymentType.STANDING_ORDER,
        failure_code=FailureCode.INSUFFICIENT_FUNDS,
        failure_reason="No funds",
        failed_at=_now(),
        customer_id="c1",
    )
    r2 = FailureRecord(
        failure_id="f-2",
        payment_id="so-1",
        payment_type=PaymentType.STANDING_ORDER,
        failure_code=FailureCode.INSUFFICIENT_FUNDS,
        failure_reason="Still no funds",
        failed_at=_now(),
        customer_id="c1",
    )
    store.save(r1)
    store.save(r2)
    assert len(store.list_by_payment("so-1")) == 2


def test_failure_store_list_by_customer() -> None:
    store = InMemoryFailureRecordStore()
    r = FailureRecord(
        failure_id="f-3",
        payment_id="so-2",
        payment_type=PaymentType.DIRECT_DEBIT,
        failure_code=FailureCode.ACCOUNT_CLOSED,
        failure_reason="Closed",
        failed_at=_now(),
        customer_id="cust-fail",
    )
    store.save(r)
    assert len(store.list_by_customer("cust-fail")) == 1
    assert len(store.list_by_customer("nobody")) == 0
