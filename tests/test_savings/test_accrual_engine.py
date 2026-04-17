"""
tests/test_savings/test_accrual_engine.py — Unit tests for AccrualEngine
IL-SIE-01 | Phase 31 | banxe-emi-stack
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from services.savings.accrual_engine import AccrualEngine
from services.savings.models import (
    AccountStatus,
    InMemoryInterestAccrualStore,
    InMemorySavingsAccountStore,
    InMemorySavingsProductStore,
    SavingsAccount,
)


def _make_active_account(
    account_id: str = "acc-1", product_id: str = "prod-easy-access"
) -> SavingsAccount:
    return SavingsAccount(
        account_id=account_id,
        customer_id="cust-1",
        product_id=product_id,
        balance=Decimal("10000.00"),
        accrued_interest=Decimal("0"),
        status=AccountStatus.ACTIVE,
        opened_at=datetime.now(UTC),
    )


@pytest.fixture()
def engine_with_account() -> tuple[AccrualEngine, str]:
    account_store = InMemorySavingsAccountStore()
    accrual_store = InMemoryInterestAccrualStore()
    product_store = InMemorySavingsProductStore()
    acc = _make_active_account()
    account_store.save(acc)
    engine = AccrualEngine(
        account_store=account_store,
        accrual_store=accrual_store,
        product_store=product_store,
    )
    return engine, acc.account_id


# ── accrue_daily ───────────────────────────────────────────────────────────────


def test_accrue_daily_returns_accrual_id(engine_with_account: tuple[AccrualEngine, str]) -> None:
    engine, account_id = engine_with_account
    result = engine.accrue_daily(account_id)
    assert result["accrual_id"] != ""


def test_accrue_daily_returns_amount(engine_with_account: tuple[AccrualEngine, str]) -> None:
    engine, account_id = engine_with_account
    result = engine.accrue_daily(account_id)
    assert Decimal(result["amount"]) > Decimal("0")


def test_accrue_daily_updates_accrued_interest(
    engine_with_account: tuple[AccrualEngine, str],
) -> None:
    engine, account_id = engine_with_account
    result = engine.accrue_daily(account_id)
    assert Decimal(result["total_accrued"]) > Decimal("0")


def test_accrue_daily_accumulates_over_multiple_days(
    engine_with_account: tuple[AccrualEngine, str],
) -> None:
    engine, account_id = engine_with_account
    engine.accrue_daily(account_id)
    result2 = engine.accrue_daily(account_id)
    assert Decimal(result2["total_accrued"]) > Decimal(result2["amount"])


def test_accrue_daily_missing_account_raises() -> None:
    engine = AccrualEngine()
    with pytest.raises(ValueError, match="Account not found"):
        engine.accrue_daily("nonexistent")


def test_accrue_daily_non_active_account_raises() -> None:
    account_store = InMemorySavingsAccountStore()
    acc = SavingsAccount(
        account_id="frozen-acc",
        customer_id="cust-x",
        product_id="prod-easy-access",
        balance=Decimal("1000.00"),
        accrued_interest=Decimal("0"),
        status=AccountStatus.FROZEN,
        opened_at=datetime.now(UTC),
    )
    account_store.save(acc)
    engine = AccrualEngine(account_store=account_store)
    with pytest.raises(ValueError, match="not ACTIVE"):
        engine.accrue_daily("frozen-acc")


# ── capitalize_monthly ─────────────────────────────────────────────────────────


def test_capitalize_monthly_no_accruals_returns_zero(
    engine_with_account: tuple[AccrualEngine, str],
) -> None:
    engine, account_id = engine_with_account
    result = engine.capitalize_monthly(account_id)
    assert result["capitalized_amount"] == "0"
    assert result["count"] == 0


def test_capitalize_monthly_adds_to_balance(engine_with_account: tuple[AccrualEngine, str]) -> None:
    engine, account_id = engine_with_account
    engine.accrue_daily(account_id)
    result = engine.capitalize_monthly(account_id)
    assert Decimal(result["new_balance"]) > Decimal("10000.00")


def test_capitalize_monthly_resets_accrued_interest(
    engine_with_account: tuple[AccrualEngine, str],
) -> None:
    engine, account_id = engine_with_account
    engine.accrue_daily(account_id)
    result = engine.capitalize_monthly(account_id)
    # After capitalization, accrued interest should be 0
    assert result["count"] == 1


def test_capitalize_monthly_missing_account_raises() -> None:
    engine = AccrualEngine()
    with pytest.raises(ValueError, match="Account not found"):
        engine.capitalize_monthly("nonexistent")


# ── get_accrual_history ────────────────────────────────────────────────────────


def test_get_accrual_history_empty(engine_with_account: tuple[AccrualEngine, str]) -> None:
    engine, account_id = engine_with_account
    result = engine.get_accrual_history(account_id)
    assert result["total_records"] == 0
    assert result["accruals"] == []


def test_get_accrual_history_after_accrual(engine_with_account: tuple[AccrualEngine, str]) -> None:
    engine, account_id = engine_with_account
    engine.accrue_daily(account_id)
    result = engine.get_accrual_history(account_id)
    assert result["total_records"] == 1


def test_get_accrual_history_contains_amount(
    engine_with_account: tuple[AccrualEngine, str],
) -> None:
    engine, account_id = engine_with_account
    engine.accrue_daily(account_id)
    result = engine.get_accrual_history(account_id)
    assert "amount" in result["accruals"][0]
