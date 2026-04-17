"""
services/scheduled_payments/models.py — Domain models and InMemory stubs for Standing Orders & Direct Debits
IL-SOD-01 | Phase 32 | banxe-emi-stack
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Protocol


class PaymentFrequency(str, Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    FORTNIGHTLY = "FORTNIGHTLY"
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    ANNUAL = "ANNUAL"


class ScheduleStatus(str, Enum):
    PENDING_AUTHORISATION = "PENDING_AUTHORISATION"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"


class DDStatus(str, Enum):
    PENDING = "PENDING"
    AUTHORISED = "AUTHORISED"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    CANCELLED = "CANCELLED"


class FailureCode(str, Enum):
    INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
    ACCOUNT_CLOSED = "ACCOUNT_CLOSED"
    ACCOUNT_BLOCKED = "ACCOUNT_BLOCKED"
    INVALID_ACCOUNT = "INVALID_ACCOUNT"
    CANCELLED_BY_PAYER = "CANCELLED_BY_PAYER"


class PaymentType(str, Enum):
    STANDING_ORDER = "STANDING_ORDER"
    DIRECT_DEBIT = "DIRECT_DEBIT"


@dataclasses.dataclass(frozen=True)
class StandingOrder:
    so_id: str
    customer_id: str
    from_account: str
    to_account: str
    amount: Decimal
    frequency: PaymentFrequency
    start_date: datetime
    next_execution_date: datetime
    status: ScheduleStatus
    reference: str
    created_at: datetime
    end_date: datetime | None = None


@dataclasses.dataclass(frozen=True)
class DirectDebit:
    dd_id: str
    mandate_id: str
    customer_id: str
    creditor_id: str
    creditor_name: str
    amount: Decimal
    status: DDStatus
    created_at: datetime
    last_executed_at: datetime | None = None


@dataclasses.dataclass(frozen=True)
class DDMandate:
    mandate_id: str
    customer_id: str
    creditor_id: str
    creditor_name: str
    scheme_ref: str
    service_user_number: str
    status: DDStatus
    created_at: datetime
    authorised_at: datetime | None = None
    cancelled_at: datetime | None = None


@dataclasses.dataclass(frozen=True)
class PaymentSchedule:
    schedule_id: str
    payment_type: PaymentType
    payment_id: str
    scheduled_at: datetime
    status: ScheduleStatus
    created_at: datetime
    executed_at: datetime | None = None


@dataclasses.dataclass(frozen=True)
class FailureRecord:
    failure_id: str
    payment_id: str
    payment_type: PaymentType
    failure_code: FailureCode
    failure_reason: str
    failed_at: datetime
    customer_id: str = ""
    retry_count: int = 0
    next_retry_at: datetime | None = None


# ── Protocols ──────────────────────────────────────────────────────────────────


class StandingOrderPort(Protocol):
    def save(self, so: StandingOrder) -> None: ...
    def update(self, so: StandingOrder) -> None: ...
    def get(self, so_id: str) -> StandingOrder | None: ...
    def list_by_customer(self, customer_id: str) -> list[StandingOrder]: ...


class DDMandatePort(Protocol):
    def save(self, mandate: DDMandate) -> None: ...
    def update(self, mandate: DDMandate) -> None: ...
    def get(self, mandate_id: str) -> DDMandate | None: ...
    def list_by_customer(self, customer_id: str) -> list[DDMandate]: ...


class PaymentSchedulePort(Protocol):
    def save(self, schedule: PaymentSchedule) -> None: ...
    def update(self, schedule: PaymentSchedule) -> None: ...
    def get(self, schedule_id: str) -> PaymentSchedule | None: ...
    def list_due(self, as_of: datetime) -> list[PaymentSchedule]: ...


class FailureRecordPort(Protocol):
    def save(self, record: FailureRecord) -> None: ...  # append-only I-24
    def list_by_payment(self, payment_id: str) -> list[FailureRecord]: ...
    def list_by_customer(self, customer_id: str) -> list[FailureRecord]: ...


# ── InMemory stubs ─────────────────────────────────────────────────────────────


class InMemoryStandingOrderStore:
    def __init__(self) -> None:
        self._data: dict[str, StandingOrder] = {}

    def save(self, so: StandingOrder) -> None:
        self._data[so.so_id] = so

    def update(self, so: StandingOrder) -> None:
        self._data[so.so_id] = so

    def get(self, so_id: str) -> StandingOrder | None:
        return self._data.get(so_id)

    def list_by_customer(self, customer_id: str) -> list[StandingOrder]:
        return [s for s in self._data.values() if s.customer_id == customer_id]


class InMemoryDDMandateStore:
    def __init__(self) -> None:
        self._data: dict[str, DDMandate] = {}

    def save(self, mandate: DDMandate) -> None:
        self._data[mandate.mandate_id] = mandate

    def update(self, mandate: DDMandate) -> None:
        self._data[mandate.mandate_id] = mandate

    def get(self, mandate_id: str) -> DDMandate | None:
        return self._data.get(mandate_id)

    def list_by_customer(self, customer_id: str) -> list[DDMandate]:
        return [m for m in self._data.values() if m.customer_id == customer_id]


class InMemoryPaymentScheduleStore:
    def __init__(self) -> None:
        self._data: dict[str, PaymentSchedule] = {}

    def save(self, schedule: PaymentSchedule) -> None:
        self._data[schedule.schedule_id] = schedule

    def update(self, schedule: PaymentSchedule) -> None:
        self._data[schedule.schedule_id] = schedule

    def get(self, schedule_id: str) -> PaymentSchedule | None:
        return self._data.get(schedule_id)

    def list_due(self, as_of: datetime) -> list[PaymentSchedule]:
        return [
            s
            for s in self._data.values()
            if s.status == ScheduleStatus.ACTIVE and s.scheduled_at <= as_of
        ]


class InMemoryFailureRecordStore:
    def __init__(self) -> None:
        self._data: list[FailureRecord] = []

    def save(self, record: FailureRecord) -> None:
        self._data.append(record)  # append-only I-24

    def list_by_payment(self, payment_id: str) -> list[FailureRecord]:
        return [r for r in self._data if r.payment_id == payment_id]

    def list_by_customer(self, customer_id: str) -> list[FailureRecord]:
        return [r for r in self._data if r.customer_id == customer_id]
