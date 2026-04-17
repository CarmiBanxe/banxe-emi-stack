"""
tests/test_savings/test_maturity_handler.py — Unit tests for MaturityHandler
IL-SIE-01 | Phase 31 | banxe-emi-stack
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from services.savings.maturity_handler import MaturityHandler
from services.savings.models import (
    AccountStatus,
    InMemorySavingsAccountStore,
    InMemorySavingsProductStore,
    MaturityAction,
    SavingsAccount,
    SavingsAccountType,
)


def _fixed_account(
    account_id: str = "acc-fixed",
    account_type: SavingsAccountType = SavingsAccountType.FIXED_TERM_12M,
    product_id: str = "prod-fixed-12m",
) -> tuple[SavingsAccount, InMemorySavingsAccountStore, InMemorySavingsProductStore]:
    account_store = InMemorySavingsAccountStore()
    product_store = InMemorySavingsProductStore()
    acc = SavingsAccount(
        account_id=account_id,
        customer_id="cust-1",
        product_id=product_id,
        balance=Decimal("10000.00"),
        accrued_interest=Decimal("50.00"),
        status=AccountStatus.ACTIVE,
        opened_at=datetime.now(UTC),
        maturity_date=datetime.now(UTC) + timedelta(days=1),
    )
    account_store.save(acc)
    return acc, account_store, product_store


# ── set_maturity_preference ────────────────────────────────────────────────────


def test_set_maturity_preference_returns_schedule_id() -> None:
    acc, acc_store, prod_store = _fixed_account()
    handler = MaturityHandler(account_store=acc_store, product_store=prod_store)
    result = handler.set_maturity_preference(acc.account_id, MaturityAction.AUTO_RENEW)
    assert result["schedule_id"] != ""


def test_set_maturity_preference_returns_action() -> None:
    acc, acc_store, prod_store = _fixed_account()
    handler = MaturityHandler(account_store=acc_store, product_store=prod_store)
    result = handler.set_maturity_preference(acc.account_id, MaturityAction.PAYOUT)
    assert result["action"] == "PAYOUT"


def test_set_maturity_preference_missing_account_raises() -> None:
    handler = MaturityHandler()
    with pytest.raises(ValueError, match="Account not found"):
        handler.set_maturity_preference("nonexistent", MaturityAction.PAYOUT)


def test_set_maturity_preference_no_maturity_date_raises() -> None:
    acc_store = InMemorySavingsAccountStore()
    acc = SavingsAccount(
        account_id="acc-no-mat",
        customer_id="cust-x",
        product_id="prod-easy-access",
        balance=Decimal("1000.00"),
        accrued_interest=Decimal("0"),
        status=AccountStatus.ACTIVE,
        opened_at=datetime.now(UTC),
        maturity_date=None,
    )
    acc_store.save(acc)
    handler = MaturityHandler(account_store=acc_store)
    with pytest.raises(ValueError, match="no maturity date"):
        handler.set_maturity_preference("acc-no-mat", MaturityAction.PAYOUT)


# ── process_maturity ────────────────────────────────────────────────────────────


def test_process_maturity_auto_renew_keeps_active() -> None:
    acc, acc_store, prod_store = _fixed_account()
    handler = MaturityHandler(account_store=acc_store, product_store=prod_store)
    handler.set_maturity_preference(acc.account_id, MaturityAction.AUTO_RENEW)
    result = handler.process_maturity(acc.account_id)
    assert result["action"] == "AUTO_RENEW"


def test_process_maturity_payout_sets_matured() -> None:
    acc, acc_store, prod_store = _fixed_account()
    handler = MaturityHandler(account_store=acc_store, product_store=prod_store)
    handler.set_maturity_preference(acc.account_id, MaturityAction.PAYOUT)
    handler.process_maturity(acc.account_id)
    updated = acc_store.get(acc.account_id)
    assert updated.status == AccountStatus.MATURED


def test_process_maturity_default_action_is_payout() -> None:
    acc, acc_store, prod_store = _fixed_account()
    handler = MaturityHandler(account_store=acc_store, product_store=prod_store)
    # No preference set → defaults to PAYOUT
    result = handler.process_maturity(acc.account_id)
    assert result["action"] == "PAYOUT"


def test_process_maturity_non_active_raises() -> None:
    acc_store = InMemorySavingsAccountStore()
    acc = SavingsAccount(
        account_id="closed-acc",
        customer_id="c1",
        product_id="prod-fixed-12m",
        balance=Decimal("1000.00"),
        accrued_interest=Decimal("0"),
        status=AccountStatus.CLOSED,
        opened_at=datetime.now(UTC),
        maturity_date=datetime.now(UTC) + timedelta(days=1),
    )
    acc_store.save(acc)
    handler = MaturityHandler(account_store=acc_store)
    with pytest.raises(ValueError, match="not ACTIVE"):
        handler.process_maturity("closed-acc")


def test_process_maturity_returns_balance() -> None:
    acc, acc_store, prod_store = _fixed_account()
    handler = MaturityHandler(account_store=acc_store, product_store=prod_store)
    result = handler.process_maturity(acc.account_id)
    assert result["balance"] == "10000.00"


# ── calculate_early_withdrawal_penalty ────────────────────────────────────────


def test_penalty_fixed_12m_has_90_days() -> None:
    acc, acc_store, prod_store = _fixed_account(product_id="prod-fixed-12m")
    handler = MaturityHandler(account_store=acc_store, product_store=prod_store)
    penalty = handler.calculate_early_withdrawal_penalty(acc.account_id)
    assert penalty.penalty_days == 90


def test_penalty_fixed_6m_has_60_days() -> None:
    acc, acc_store, prod_store = _fixed_account(
        product_id="prod-fixed-6m",
        account_type=SavingsAccountType.FIXED_TERM_6M,
    )
    handler = MaturityHandler(account_store=acc_store, product_store=prod_store)
    penalty = handler.calculate_early_withdrawal_penalty(acc.account_id)
    assert penalty.penalty_days == 60


def test_penalty_fixed_3m_has_30_days() -> None:
    acc, acc_store, prod_store = _fixed_account(
        product_id="prod-fixed-3m",
        account_type=SavingsAccountType.FIXED_TERM_3M,
    )
    handler = MaturityHandler(account_store=acc_store, product_store=prod_store)
    penalty = handler.calculate_early_withdrawal_penalty(acc.account_id)
    assert penalty.penalty_days == 30


def test_penalty_amount_is_decimal() -> None:
    acc, acc_store, prod_store = _fixed_account()
    handler = MaturityHandler(account_store=acc_store, product_store=prod_store)
    penalty = handler.calculate_early_withdrawal_penalty(acc.account_id)
    assert isinstance(penalty.penalty_amount, Decimal)


def test_penalty_missing_account_raises() -> None:
    handler = MaturityHandler()
    with pytest.raises(ValueError, match="Account not found"):
        handler.calculate_early_withdrawal_penalty("nonexistent")
