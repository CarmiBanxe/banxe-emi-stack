"""
services/savings/models.py — Domain models and InMemory stubs for Savings & Interest Engine
IL-SIE-01 | Phase 31 | banxe-emi-stack
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Protocol


class SavingsAccountType(str, Enum):
    EASY_ACCESS = "EASY_ACCESS"
    FIXED_TERM_3M = "FIXED_TERM_3M"
    FIXED_TERM_6M = "FIXED_TERM_6M"
    FIXED_TERM_12M = "FIXED_TERM_12M"
    NOTICE_30D = "NOTICE_30D"
    NOTICE_60D = "NOTICE_60D"
    NOTICE_90D = "NOTICE_90D"


class AccountStatus(str, Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    FROZEN = "FROZEN"
    CLOSED = "CLOSED"
    MATURED = "MATURED"


class InterestBasis(str, Enum):
    DAILY = "DAILY"
    MONTHLY = "MONTHLY"
    ANNUAL = "ANNUAL"


class InterestType(str, Enum):
    COMPOUND = "COMPOUND"
    SIMPLE = "SIMPLE"


class MaturityAction(str, Enum):
    AUTO_RENEW = "AUTO_RENEW"
    PAYOUT = "PAYOUT"


@dataclasses.dataclass(frozen=True)
class SavingsProduct:
    product_id: str
    name: str
    account_type: SavingsAccountType
    min_deposit: Decimal
    max_deposit: Decimal
    gross_rate: Decimal
    aer: Decimal
    interest_type: InterestType
    interest_basis: InterestBasis
    tax_free: bool
    is_active: bool
    term_days: int = 0
    notice_days: int = 0


@dataclasses.dataclass(frozen=True)
class SavingsAccount:
    account_id: str
    customer_id: str
    product_id: str
    balance: Decimal
    accrued_interest: Decimal
    status: AccountStatus
    opened_at: datetime
    maturity_date: datetime | None = None
    notice_given_at: datetime | None = None
    auto_renew: bool = False
    payout_account_id: str | None = None


@dataclasses.dataclass(frozen=True)
class InterestRate:
    rate_id: str
    product_id: str
    gross_rate: Decimal
    aer: Decimal
    effective_from: datetime
    effective_to: datetime | None
    created_at: datetime


@dataclasses.dataclass(frozen=True)
class InterestAccrual:
    accrual_id: str
    account_id: str
    amount: Decimal
    period_start: datetime
    period_end: datetime
    capitalized: bool
    created_at: datetime


@dataclasses.dataclass(frozen=True)
class MaturitySchedule:
    schedule_id: str
    account_id: str
    maturity_date: datetime
    action: MaturityAction
    payout_account_id: str | None
    processed: bool
    processed_at: datetime | None


@dataclasses.dataclass(frozen=True)
class EarlyWithdrawalPenalty:
    penalty_id: str
    account_id: str
    penalty_days: int
    penalty_amount: Decimal
    calculated_at: datetime


# ── Protocols ──────────────────────────────────────────────────────────────────


class SavingsProductPort(Protocol):
    def save(self, product: SavingsProduct) -> None: ...
    def get(self, product_id: str) -> SavingsProduct | None: ...
    def list_active(self) -> list[SavingsProduct]: ...


class SavingsAccountPort(Protocol):
    def save(self, account: SavingsAccount) -> None: ...
    def update(self, account: SavingsAccount) -> None: ...
    def get(self, account_id: str) -> SavingsAccount | None: ...
    def list_by_customer(self, customer_id: str) -> list[SavingsAccount]: ...
    def list_by_status(self, status: AccountStatus) -> list[SavingsAccount]: ...


class InterestRatePort(Protocol):
    def save(self, rate: InterestRate) -> None: ...
    def get_current(self, product_id: str) -> InterestRate | None: ...
    def list_history(self, product_id: str) -> list[InterestRate]: ...


class InterestAccrualPort(Protocol):
    def save(self, accrual: InterestAccrual) -> None: ...
    def list_by_account(self, account_id: str) -> list[InterestAccrual]: ...
    def list_uncapitalized(self, account_id: str) -> list[InterestAccrual]: ...


# ── InMemory stubs ─────────────────────────────────────────────────────────────


class InMemorySavingsProductStore:
    def __init__(self) -> None:
        self._data: dict[str, SavingsProduct] = {}
        for p in _default_products():
            self._data[p.product_id] = p

    def save(self, product: SavingsProduct) -> None:
        self._data[product.product_id] = product

    def get(self, product_id: str) -> SavingsProduct | None:
        return self._data.get(product_id)

    def list_active(self) -> list[SavingsProduct]:
        return [p for p in self._data.values() if p.is_active]


class InMemorySavingsAccountStore:
    def __init__(self) -> None:
        self._data: dict[str, SavingsAccount] = {}

    def save(self, account: SavingsAccount) -> None:
        self._data[account.account_id] = account

    def update(self, account: SavingsAccount) -> None:
        self._data[account.account_id] = account

    def get(self, account_id: str) -> SavingsAccount | None:
        return self._data.get(account_id)

    def list_by_customer(self, customer_id: str) -> list[SavingsAccount]:
        return [a for a in self._data.values() if a.customer_id == customer_id]

    def list_by_status(self, status: AccountStatus) -> list[SavingsAccount]:
        return [a for a in self._data.values() if a.status == status]


class InMemoryInterestRateStore:
    def __init__(self) -> None:
        self._data: list[InterestRate] = []

    def save(self, rate: InterestRate) -> None:
        self._data.append(rate)

    def get_current(self, product_id: str) -> InterestRate | None:
        matching = [r for r in self._data if r.product_id == product_id and r.effective_to is None]
        return matching[-1] if matching else None

    def list_history(self, product_id: str) -> list[InterestRate]:
        return [r for r in self._data if r.product_id == product_id]


class InMemoryInterestAccrualStore:
    def __init__(self) -> None:
        self._data: list[InterestAccrual] = []

    def save(self, accrual: InterestAccrual) -> None:
        self._data.append(accrual)  # append-only I-24

    def list_by_account(self, account_id: str) -> list[InterestAccrual]:
        return [a for a in self._data if a.account_id == account_id]

    def list_uncapitalized(self, account_id: str) -> list[InterestAccrual]:
        return [a for a in self._data if a.account_id == account_id and not a.capitalized]


# ── Seed data ──────────────────────────────────────────────────────────────────


def _default_products() -> list[SavingsProduct]:
    return [
        SavingsProduct(
            product_id="prod-easy-access",
            name="Easy Access Savings",
            account_type=SavingsAccountType.EASY_ACCESS,
            min_deposit=Decimal("1.00"),
            max_deposit=Decimal("250000.00"),
            gross_rate=Decimal("0.043"),
            aer=Decimal("0.045"),
            interest_type=InterestType.COMPOUND,
            interest_basis=InterestBasis.DAILY,
            tax_free=False,
            is_active=True,
            term_days=0,
            notice_days=0,
        ),
        SavingsProduct(
            product_id="prod-fixed-3m",
            name="Fixed Term 3 Month",
            account_type=SavingsAccountType.FIXED_TERM_3M,
            min_deposit=Decimal("500.00"),
            max_deposit=Decimal("500000.00"),
            gross_rate=Decimal("0.047"),
            aer=Decimal("0.048"),
            interest_type=InterestType.COMPOUND,
            interest_basis=InterestBasis.DAILY,
            tax_free=False,
            is_active=True,
            term_days=91,
            notice_days=0,
        ),
        SavingsProduct(
            product_id="prod-fixed-6m",
            name="Fixed Term 6 Month",
            account_type=SavingsAccountType.FIXED_TERM_6M,
            min_deposit=Decimal("500.00"),
            max_deposit=Decimal("500000.00"),
            gross_rate=Decimal("0.049"),
            aer=Decimal("0.050"),
            interest_type=InterestType.COMPOUND,
            interest_basis=InterestBasis.DAILY,
            tax_free=False,
            is_active=True,
            term_days=182,
            notice_days=0,
        ),
        SavingsProduct(
            product_id="prod-fixed-12m",
            name="Fixed Term 12 Month",
            account_type=SavingsAccountType.FIXED_TERM_12M,
            min_deposit=Decimal("500.00"),
            max_deposit=Decimal("500000.00"),
            gross_rate=Decimal("0.051"),
            aer=Decimal("0.052"),
            interest_type=InterestType.COMPOUND,
            interest_basis=InterestBasis.DAILY,
            tax_free=False,
            is_active=True,
            term_days=365,
            notice_days=0,
        ),
        SavingsProduct(
            product_id="prod-notice-30d",
            name="30-Day Notice Account",
            account_type=SavingsAccountType.NOTICE_30D,
            min_deposit=Decimal("100.00"),
            max_deposit=Decimal("250000.00"),
            gross_rate=Decimal("0.046"),
            aer=Decimal("0.047"),
            interest_type=InterestType.COMPOUND,
            interest_basis=InterestBasis.DAILY,
            tax_free=False,
            is_active=True,
            term_days=0,
            notice_days=30,
        ),
    ]
