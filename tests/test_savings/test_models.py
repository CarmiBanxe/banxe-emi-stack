"""
tests/test_savings/test_models.py — Unit tests for savings domain models
IL-SIE-01 | Phase 31 | banxe-emi-stack
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from decimal import Decimal
import uuid

import pytest

from services.savings.models import (
    AccountStatus,
    InMemoryInterestAccrualStore,
    InMemoryInterestRateStore,
    InMemorySavingsAccountStore,
    InMemorySavingsProductStore,
    InterestAccrual,
    InterestBasis,
    InterestRate,
    InterestType,
    MaturityAction,
    SavingsAccount,
    SavingsAccountType,
    SavingsProduct,
)


def _now() -> datetime:
    return datetime.now(UTC)


# ── Enum tests ─────────────────────────────────────────────────────────────────


def test_savings_account_type_values() -> None:
    assert SavingsAccountType.EASY_ACCESS.value == "EASY_ACCESS"
    assert SavingsAccountType.FIXED_TERM_3M.value == "FIXED_TERM_3M"
    assert SavingsAccountType.FIXED_TERM_6M.value == "FIXED_TERM_6M"
    assert SavingsAccountType.FIXED_TERM_12M.value == "FIXED_TERM_12M"
    assert SavingsAccountType.NOTICE_30D.value == "NOTICE_30D"
    assert SavingsAccountType.NOTICE_60D.value == "NOTICE_60D"
    assert SavingsAccountType.NOTICE_90D.value == "NOTICE_90D"


def test_account_status_values() -> None:
    assert AccountStatus.PENDING.value == "PENDING"
    assert AccountStatus.ACTIVE.value == "ACTIVE"
    assert AccountStatus.FROZEN.value == "FROZEN"
    assert AccountStatus.CLOSED.value == "CLOSED"
    assert AccountStatus.MATURED.value == "MATURED"


def test_interest_basis_values() -> None:
    assert InterestBasis.DAILY.value == "DAILY"
    assert InterestBasis.MONTHLY.value == "MONTHLY"
    assert InterestBasis.ANNUAL.value == "ANNUAL"


def test_interest_type_values() -> None:
    assert InterestType.COMPOUND.value == "COMPOUND"
    assert InterestType.SIMPLE.value == "SIMPLE"


def test_maturity_action_values() -> None:
    assert MaturityAction.AUTO_RENEW.value == "AUTO_RENEW"
    assert MaturityAction.PAYOUT.value == "PAYOUT"


# ── SavingsProduct dataclass ────────────────────────────────────────────────────


def test_savings_product_creation() -> None:
    p = SavingsProduct(
        product_id="p-1",
        name="Test",
        account_type=SavingsAccountType.EASY_ACCESS,
        min_deposit=Decimal("1.00"),
        max_deposit=Decimal("250000.00"),
        gross_rate=Decimal("0.043"),
        aer=Decimal("0.045"),
        interest_type=InterestType.COMPOUND,
        interest_basis=InterestBasis.DAILY,
        tax_free=False,
        is_active=True,
    )
    assert p.min_deposit == Decimal("1.00")
    assert p.term_days == 0
    assert p.notice_days == 0


def test_savings_product_frozen() -> None:
    p = SavingsProduct(
        product_id="p-2",
        name="Test",
        account_type=SavingsAccountType.EASY_ACCESS,
        min_deposit=Decimal("1.00"),
        max_deposit=Decimal("100.00"),
        gross_rate=Decimal("0.04"),
        aer=Decimal("0.04"),
        interest_type=InterestType.SIMPLE,
        interest_basis=InterestBasis.ANNUAL,
        tax_free=False,
        is_active=True,
    )
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        p.name = "Modified"  # type: ignore[misc]


# ── InMemorySavingsProductStore seeded data ────────────────────────────────────


def test_product_store_seeded_count() -> None:
    store = InMemorySavingsProductStore()
    assert len(store.list_active()) == 5


def test_product_store_easy_access() -> None:
    store = InMemorySavingsProductStore()
    p = store.get("prod-easy-access")
    assert p is not None
    assert p.gross_rate == Decimal("0.043")
    assert p.aer == Decimal("0.045")
    assert p.min_deposit == Decimal("1.00")


def test_product_store_fixed_3m() -> None:
    store = InMemorySavingsProductStore()
    p = store.get("prod-fixed-3m")
    assert p is not None
    assert p.term_days == 91
    assert p.aer == Decimal("0.048")


def test_product_store_fixed_6m() -> None:
    store = InMemorySavingsProductStore()
    p = store.get("prod-fixed-6m")
    assert p is not None
    assert p.term_days == 182


def test_product_store_fixed_12m() -> None:
    store = InMemorySavingsProductStore()
    p = store.get("prod-fixed-12m")
    assert p is not None
    assert p.term_days == 365
    assert p.aer == Decimal("0.052")


def test_product_store_notice_30d() -> None:
    store = InMemorySavingsProductStore()
    p = store.get("prod-notice-30d")
    assert p is not None
    assert p.notice_days == 30
    assert p.aer == Decimal("0.047")


def test_product_store_get_missing() -> None:
    store = InMemorySavingsProductStore()
    assert store.get("nonexistent") is None


def test_product_store_save_and_get() -> None:
    store = InMemorySavingsProductStore()
    p = SavingsProduct(
        product_id="prod-new",
        name="New",
        account_type=SavingsAccountType.EASY_ACCESS,
        min_deposit=Decimal("50.00"),
        max_deposit=Decimal("10000.00"),
        gross_rate=Decimal("0.03"),
        aer=Decimal("0.03"),
        interest_type=InterestType.SIMPLE,
        interest_basis=InterestBasis.ANNUAL,
        tax_free=False,
        is_active=True,
    )
    store.save(p)
    assert store.get("prod-new") is not None


# ── InMemorySavingsAccountStore ────────────────────────────────────────────────


def test_account_store_save_and_get() -> None:
    store = InMemorySavingsAccountStore()
    acc = SavingsAccount(
        account_id="acc-1",
        customer_id="cust-1",
        product_id="prod-easy-access",
        balance=Decimal("1000.00"),
        accrued_interest=Decimal("0"),
        status=AccountStatus.ACTIVE,
        opened_at=_now(),
    )
    store.save(acc)
    result = store.get("acc-1")
    assert result is not None
    assert result.customer_id == "cust-1"


def test_account_store_update() -> None:
    store = InMemorySavingsAccountStore()
    acc = SavingsAccount(
        account_id="acc-2",
        customer_id="cust-2",
        product_id="prod-easy-access",
        balance=Decimal("500.00"),
        accrued_interest=Decimal("0"),
        status=AccountStatus.ACTIVE,
        opened_at=_now(),
    )
    store.save(acc)
    updated = dataclasses.replace(acc, balance=Decimal("600.00"))
    store.update(updated)
    assert store.get("acc-2").balance == Decimal("600.00")


def test_account_store_list_by_customer() -> None:
    store = InMemorySavingsAccountStore()
    acc = SavingsAccount(
        account_id="acc-3",
        customer_id="cust-3",
        product_id="prod-easy-access",
        balance=Decimal("100.00"),
        accrued_interest=Decimal("0"),
        status=AccountStatus.ACTIVE,
        opened_at=_now(),
    )
    store.save(acc)
    assert len(store.list_by_customer("cust-3")) == 1
    assert len(store.list_by_customer("nobody")) == 0


def test_account_store_list_by_status() -> None:
    store = InMemorySavingsAccountStore()
    acc = SavingsAccount(
        account_id="acc-4",
        customer_id="cust-4",
        product_id="prod-fixed-12m",
        balance=Decimal("1000.00"),
        accrued_interest=Decimal("0"),
        status=AccountStatus.MATURED,
        opened_at=_now(),
    )
    store.save(acc)
    assert len(store.list_by_status(AccountStatus.MATURED)) == 1
    assert len(store.list_by_status(AccountStatus.ACTIVE)) == 0


# ── InMemoryInterestRateStore ──────────────────────────────────────────────────


def test_rate_store_get_current_empty() -> None:
    store = InMemoryInterestRateStore()
    assert store.get_current("prod-1") is None


def test_rate_store_save_and_get_current() -> None:
    store = InMemoryInterestRateStore()
    rate = InterestRate(
        rate_id=str(uuid.uuid4()),
        product_id="prod-1",
        gross_rate=Decimal("0.05"),
        aer=Decimal("0.051"),
        effective_from=_now(),
        effective_to=None,
        created_at=_now(),
    )
    store.save(rate)
    current = store.get_current("prod-1")
    assert current is not None
    assert current.gross_rate == Decimal("0.05")


def test_rate_store_list_history() -> None:
    store = InMemoryInterestRateStore()
    r1 = InterestRate(
        rate_id=str(uuid.uuid4()),
        product_id="prod-2",
        gross_rate=Decimal("0.04"),
        aer=Decimal("0.041"),
        effective_from=_now(),
        effective_to=_now(),
        created_at=_now(),
    )
    r2 = InterestRate(
        rate_id=str(uuid.uuid4()),
        product_id="prod-2",
        gross_rate=Decimal("0.05"),
        aer=Decimal("0.051"),
        effective_from=_now(),
        effective_to=None,
        created_at=_now(),
    )
    store.save(r1)
    store.save(r2)
    history = store.list_history("prod-2")
    assert len(history) == 2


# ── InMemoryInterestAccrualStore (append-only I-24) ────────────────────────────


def test_accrual_store_save_is_append_only() -> None:
    store = InMemoryInterestAccrualStore()
    a1 = InterestAccrual(
        accrual_id="acr-1",
        account_id="acc-1",
        amount=Decimal("0.12345678"),
        period_start=_now(),
        period_end=_now(),
        capitalized=False,
        created_at=_now(),
    )
    a2 = InterestAccrual(
        accrual_id="acr-2",
        account_id="acc-1",
        amount=Decimal("0.11111111"),
        period_start=_now(),
        period_end=_now(),
        capitalized=False,
        created_at=_now(),
    )
    store.save(a1)
    store.save(a2)
    assert len(store.list_by_account("acc-1")) == 2


def test_accrual_store_list_uncapitalized() -> None:
    store = InMemoryInterestAccrualStore()
    uncap = InterestAccrual(
        accrual_id="acr-3",
        account_id="acc-2",
        amount=Decimal("0.10000000"),
        period_start=_now(),
        period_end=_now(),
        capitalized=False,
        created_at=_now(),
    )
    cap = InterestAccrual(
        accrual_id="acr-4",
        account_id="acc-2",
        amount=Decimal("0.10000000"),
        period_start=_now(),
        period_end=_now(),
        capitalized=True,
        created_at=_now(),
    )
    store.save(uncap)
    store.save(cap)
    result = store.list_uncapitalized("acc-2")
    assert len(result) == 1
    assert result[0].capitalized is False
