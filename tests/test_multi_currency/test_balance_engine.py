"""tests/test_multi_currency/test_balance_engine.py — BalanceEngine tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.multi_currency.account_manager import AccountManager
from services.multi_currency.balance_engine import BalanceEngine
from services.multi_currency.models import (
    InMemoryAccountStore,
    InMemoryLedgerEntryStore,
    InMemoryMCAudit,
)


def _make_stores():
    account_store = InMemoryAccountStore()
    ledger_store = InMemoryLedgerEntryStore()
    audit = InMemoryMCAudit()
    return account_store, ledger_store, audit


async def _create_account_with_balances(currencies: list[str], base: str = "GBP"):
    account_store, ledger_store, audit = _make_stores()
    mgr = AccountManager(account_store, ledger_store, audit)
    engine = BalanceEngine(account_store, ledger_store)
    acct = await mgr.create_account("ent-001", base, currencies)
    return acct, engine


# ── get_balance ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_balance_returns_zero_for_new_account() -> None:
    acct, engine = await _create_account_with_balances(["EUR"])
    bal = await engine.get_balance(acct.account_id, "GBP")
    assert bal is not None
    assert bal.amount == Decimal("0")


@pytest.mark.asyncio
async def test_get_balance_returns_none_for_unknown_account() -> None:
    _, engine = await _create_account_with_balances([])
    bal = await engine.get_balance("nonexistent", "GBP")
    assert bal is None


@pytest.mark.asyncio
async def test_get_balance_returns_none_for_missing_currency() -> None:
    acct, engine = await _create_account_with_balances([])
    bal = await engine.get_balance(acct.account_id, "USD")
    assert bal is None


# ── credit ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_credit_increases_balance() -> None:
    acct, engine = await _create_account_with_balances([])
    await engine.credit(acct.account_id, "GBP", Decimal("500"), "deposit")
    bal = await engine.get_balance(acct.account_id, "GBP")
    assert bal is not None
    assert bal.amount == Decimal("500")
    assert bal.available == Decimal("500")


@pytest.mark.asyncio
async def test_credit_creates_ledger_entry() -> None:
    acct, engine = await _create_account_with_balances([])
    await engine.credit(acct.account_id, "GBP", Decimal("100"), "test")
    entries = await engine.get_ledger_entries(acct.account_id)
    assert len(entries) == 1
    assert entries[0].direction == "CREDIT"
    assert entries[0].amount == Decimal("100")


@pytest.mark.asyncio
async def test_credit_multiple_times_accumulates() -> None:
    acct, engine = await _create_account_with_balances([])
    await engine.credit(acct.account_id, "GBP", Decimal("100"), "first")
    await engine.credit(acct.account_id, "GBP", Decimal("200"), "second")
    bal = await engine.get_balance(acct.account_id, "GBP")
    assert bal is not None
    assert bal.amount == Decimal("300")


# ── debit ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_debit_decreases_balance() -> None:
    acct, engine = await _create_account_with_balances([])
    await engine.credit(acct.account_id, "GBP", Decimal("500"), "fund")
    await engine.debit(acct.account_id, "GBP", Decimal("200"), "payment")
    bal = await engine.get_balance(acct.account_id, "GBP")
    assert bal is not None
    assert bal.amount == Decimal("300")


@pytest.mark.asyncio
async def test_debit_creates_ledger_entry() -> None:
    acct, engine = await _create_account_with_balances([])
    await engine.credit(acct.account_id, "GBP", Decimal("500"), "fund")
    await engine.debit(acct.account_id, "GBP", Decimal("100"), "withdraw")
    entries = await engine.get_ledger_entries(acct.account_id)
    debit_entries = [e for e in entries if e.direction == "DEBIT"]
    assert len(debit_entries) == 1


@pytest.mark.asyncio
async def test_debit_insufficient_balance_raises() -> None:
    acct, engine = await _create_account_with_balances([])
    await engine.credit(acct.account_id, "GBP", Decimal("50"), "fund")
    with pytest.raises(ValueError, match="Insufficient balance"):
        await engine.debit(acct.account_id, "GBP", Decimal("100"), "payment")


@pytest.mark.asyncio
async def test_debit_exact_balance_ok() -> None:
    acct, engine = await _create_account_with_balances([])
    await engine.credit(acct.account_id, "GBP", Decimal("100"), "fund")
    await engine.debit(acct.account_id, "GBP", Decimal("100"), "full withdrawal")
    bal = await engine.get_balance(acct.account_id, "GBP")
    assert bal is not None
    assert bal.amount == Decimal("0")


# ── get_consolidated_balance ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_consolidated_balance_single_currency() -> None:
    acct, engine = await _create_account_with_balances([])
    await engine.credit(acct.account_id, "GBP", Decimal("1000"), "fund")
    total = await engine.get_consolidated_balance(acct.account_id, {})
    assert total == Decimal("1000")


@pytest.mark.asyncio
async def test_consolidated_balance_multi_currency() -> None:
    acct, engine = await _create_account_with_balances(["EUR"])
    await engine.credit(acct.account_id, "GBP", Decimal("1000"), "fund")
    await engine.credit(acct.account_id, "EUR", Decimal("500"), "fund eur")
    # rate EUR→GBP = 0.85
    total = await engine.get_consolidated_balance(acct.account_id, {"EUR": Decimal("0.85")})
    assert total == Decimal("1000") + Decimal("500") * Decimal("0.85")


@pytest.mark.asyncio
async def test_consolidated_balance_missing_rate_raises() -> None:
    acct, engine = await _create_account_with_balances(["EUR"])
    await engine.credit(acct.account_id, "EUR", Decimal("100"), "fund")
    with pytest.raises(ValueError, match="Missing FX rate"):
        await engine.get_consolidated_balance(acct.account_id, {})


# ── get_ledger_entries ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ledger_entries_filtered_by_currency() -> None:
    acct, engine = await _create_account_with_balances(["EUR"])
    await engine.credit(acct.account_id, "GBP", Decimal("100"), "gbp")
    await engine.credit(acct.account_id, "EUR", Decimal("200"), "eur")
    gbp_entries = await engine.get_ledger_entries(acct.account_id, "GBP")
    assert len(gbp_entries) == 1
    assert gbp_entries[0].currency == "GBP"


@pytest.mark.asyncio
async def test_ledger_entries_all_currencies() -> None:
    acct, engine = await _create_account_with_balances(["EUR"])
    await engine.credit(acct.account_id, "GBP", Decimal("100"), "gbp")
    await engine.credit(acct.account_id, "EUR", Decimal("200"), "eur")
    all_entries = await engine.get_ledger_entries(acct.account_id)
    assert len(all_entries) == 2


# ── get_all_balances ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_all_balances_returns_all_currencies() -> None:
    acct, engine = await _create_account_with_balances(["EUR", "USD"])
    balances = await engine.get_all_balances(acct.account_id)
    currencies = {b.currency for b in balances}
    assert "GBP" in currencies
    assert "EUR" in currencies
    assert "USD" in currencies


@pytest.mark.asyncio
async def test_get_all_balances_empty_for_unknown_account() -> None:
    _, engine = await _create_account_with_balances([])
    balances = await engine.get_all_balances("unknown")
    assert balances == []
