"""
tests/test_savings/test_savings_agent.py — Unit tests for SavingsAgent
IL-SIE-01 | Phase 31 | banxe-emi-stack
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.savings.models import (
    InMemorySavingsProductStore,
    InterestBasis,
    InterestType,
    SavingsAccountType,
    SavingsProduct,
)
from services.savings.savings_agent import SavingsAgent


@pytest.fixture()
def agent() -> SavingsAgent:
    return SavingsAgent()


def _open_account(
    agent: SavingsAgent, product_id: str = "prod-easy-access", amount: str = "1000.00"
) -> str:
    result = agent.open_account("cust-1", product_id, Decimal(amount))
    return result["account_id"]


# ── open_account ───────────────────────────────────────────────────────────────


def test_open_account_returns_account_id(agent: SavingsAgent) -> None:
    result = agent.open_account("cust-1", "prod-easy-access", Decimal("1000.00"))
    assert result["account_id"] != ""


def test_open_account_status_active(agent: SavingsAgent) -> None:
    result = agent.open_account("cust-1", "prod-easy-access", Decimal("1000.00"))
    assert result["status"] == "ACTIVE"


def test_open_account_fixed_term_sets_maturity_date(agent: SavingsAgent) -> None:
    result = agent.open_account("cust-1", "prod-fixed-12m", Decimal("1000.00"))
    assert result["maturity_date"] is not None


def test_open_account_easy_access_no_maturity(agent: SavingsAgent) -> None:
    result = agent.open_account("cust-1", "prod-easy-access", Decimal("1000.00"))
    assert result["maturity_date"] is None


def test_open_account_below_min_deposit_raises(agent: SavingsAgent) -> None:
    with pytest.raises(ValueError, match="below minimum"):
        agent.open_account("cust-1", "prod-fixed-12m", Decimal("100.00"))


def test_open_account_above_max_deposit_raises(agent: SavingsAgent) -> None:
    with pytest.raises(ValueError, match="above maximum"):
        agent.open_account("cust-1", "prod-easy-access", Decimal("999999.00"))


def test_open_account_unknown_product_raises(agent: SavingsAgent) -> None:
    with pytest.raises(ValueError, match="Product not found"):
        agent.open_account("cust-1", "nonexistent", Decimal("1000.00"))


def test_open_account_inactive_product_raises() -> None:
    product_store = InMemorySavingsProductStore()
    inactive = SavingsProduct(
        product_id="prod-inactive",
        name="Inactive",
        account_type=SavingsAccountType.EASY_ACCESS,
        min_deposit=Decimal("1.00"),
        max_deposit=Decimal("100000.00"),
        gross_rate=Decimal("0.01"),
        aer=Decimal("0.01"),
        interest_type=InterestType.SIMPLE,
        interest_basis=InterestBasis.ANNUAL,
        tax_free=False,
        is_active=False,
    )
    product_store.save(inactive)
    agent = SavingsAgent(product_store=product_store)
    with pytest.raises(ValueError, match="not active"):
        agent.open_account("cust-1", "prod-inactive", Decimal("100.00"))


def test_open_account_returns_balance(agent: SavingsAgent) -> None:
    result = agent.open_account("cust-1", "prod-easy-access", Decimal("5000.00"))
    assert result["balance"] == "5000.00"


# ── deposit ────────────────────────────────────────────────────────────────────


def test_deposit_increases_balance(agent: SavingsAgent) -> None:
    account_id = _open_account(agent)
    result = agent.deposit(account_id, Decimal("500.00"))
    assert result["new_balance"] == "1500.00"


def test_deposit_returns_status_deposited(agent: SavingsAgent) -> None:
    account_id = _open_account(agent)
    result = agent.deposit(account_id, Decimal("100.00"))
    assert result["status"] == "DEPOSITED"


def test_deposit_zero_raises(agent: SavingsAgent) -> None:
    account_id = _open_account(agent)
    with pytest.raises(ValueError, match="must be positive"):
        agent.deposit(account_id, Decimal("0"))


def test_deposit_negative_raises(agent: SavingsAgent) -> None:
    account_id = _open_account(agent)
    with pytest.raises(ValueError, match="must be positive"):
        agent.deposit(account_id, Decimal("-100"))


def test_deposit_missing_account_raises(agent: SavingsAgent) -> None:
    with pytest.raises(ValueError, match="Account not found"):
        agent.deposit("nonexistent", Decimal("100.00"))


def test_deposit_exceeds_max_raises(agent: SavingsAgent) -> None:
    account_id = _open_account(agent, "prod-easy-access", "249000.00")
    with pytest.raises(ValueError, match="exceed maximum"):
        agent.deposit(account_id, Decimal("2000.00"))


# ── withdraw ───────────────────────────────────────────────────────────────────


def test_withdraw_reduces_balance(agent: SavingsAgent) -> None:
    account_id = _open_account(agent)
    result = agent.withdraw(account_id, Decimal("300.00"))
    assert result["new_balance"] == "700.00"


def test_withdraw_returns_status_withdrawn(agent: SavingsAgent) -> None:
    account_id = _open_account(agent)
    result = agent.withdraw(account_id, Decimal("100.00"))
    assert result["status"] == "WITHDRAWN"


def test_withdraw_more_than_balance_raises(agent: SavingsAgent) -> None:
    account_id = _open_account(agent)
    with pytest.raises(ValueError, match="Insufficient balance"):
        agent.withdraw(account_id, Decimal("9999.00"))


def test_withdraw_zero_raises(agent: SavingsAgent) -> None:
    account_id = _open_account(agent)
    with pytest.raises(ValueError, match="must be positive"):
        agent.withdraw(account_id, Decimal("0"))


def test_withdraw_missing_account_raises(agent: SavingsAgent) -> None:
    with pytest.raises(ValueError, match="Account not found"):
        agent.withdraw("nonexistent", Decimal("100.00"))


def test_withdraw_large_amount_from_fixed_term_hitl(agent: SavingsAgent) -> None:
    account_id = _open_account(agent, "prod-fixed-12m", "100000.00")
    result = agent.withdraw(account_id, Decimal("50000.00"))
    assert result["status"] == "HITL_REQUIRED"


def test_withdraw_below_threshold_from_fixed_term_allowed(agent: SavingsAgent) -> None:
    account_id = _open_account(agent, "prod-fixed-12m", "10000.00")
    result = agent.withdraw(account_id, Decimal("1000.00"))
    assert result["status"] == "WITHDRAWN"


def test_withdraw_large_from_easy_access_no_hitl(agent: SavingsAgent) -> None:
    # Easy access is not fixed-term → no HITL even for large amounts
    account_id = _open_account(agent, "prod-easy-access", "100000.00")
    result = agent.withdraw(account_id, Decimal("50000.00"))
    assert result["status"] == "WITHDRAWN"


# ── get_interest_summary ───────────────────────────────────────────────────────


def test_get_interest_summary_returns_balance(agent: SavingsAgent) -> None:
    account_id = _open_account(agent)
    result = agent.get_interest_summary(account_id)
    assert result["balance"] == "1000.00"


def test_get_interest_summary_returns_gross_rate(agent: SavingsAgent) -> None:
    account_id = _open_account(agent)
    result = agent.get_interest_summary(account_id)
    assert "gross_rate" in result


def test_get_interest_summary_returns_aer(agent: SavingsAgent) -> None:
    account_id = _open_account(agent)
    result = agent.get_interest_summary(account_id)
    assert "aer" in result


def test_get_interest_summary_returns_daily_interest(agent: SavingsAgent) -> None:
    account_id = _open_account(agent)
    result = agent.get_interest_summary(account_id)
    assert Decimal(result["daily_interest"]) > Decimal("0")


def test_get_interest_summary_returns_tax_info(agent: SavingsAgent) -> None:
    account_id = _open_account(agent)
    result = agent.get_interest_summary(account_id)
    assert "tax_info" in result


def test_get_interest_summary_missing_account_raises(agent: SavingsAgent) -> None:
    with pytest.raises(ValueError, match="Account not found"):
        agent.get_interest_summary("nonexistent")


# ── get_account / list_accounts ────────────────────────────────────────────────


def test_get_account_returns_all_fields(agent: SavingsAgent) -> None:
    account_id = _open_account(agent)
    result = agent.get_account(account_id)
    assert result["account_id"] == account_id
    assert result["status"] == "ACTIVE"


def test_list_accounts_returns_correct_count(agent: SavingsAgent) -> None:
    agent.open_account("cust-list", "prod-easy-access", Decimal("1000.00"))
    agent.open_account("cust-list", "prod-fixed-3m", Decimal("500.00"))
    result = agent.list_accounts("cust-list")
    assert result["count"] == 2


def test_list_accounts_empty_for_new_customer(agent: SavingsAgent) -> None:
    result = agent.list_accounts("brand-new-customer")
    assert result["count"] == 0
