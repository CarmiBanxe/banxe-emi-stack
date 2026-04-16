"""tests/test_multi_currency/test_multicurrency_agent.py — MultiCurrencyAgent tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.multi_currency.account_manager import AccountManager
from services.multi_currency.balance_engine import BalanceEngine
from services.multi_currency.conversion_tracker import ConversionTracker
from services.multi_currency.currency_router import CurrencyRouter
from services.multi_currency.models import (
    InMemoryAccountStore,
    InMemoryConversionStore,
    InMemoryLedgerEntryStore,
    InMemoryMCAudit,
    InMemoryNostroStore,
)
from services.multi_currency.multicurrency_agent import MultiCurrencyAgent
from services.multi_currency.nostro_reconciler import NostroReconciler


def _make_agent() -> MultiCurrencyAgent:
    account_store = InMemoryAccountStore()
    ledger_store = InMemoryLedgerEntryStore()
    conversion_store = InMemoryConversionStore()
    nostro_store = InMemoryNostroStore()
    audit = InMemoryMCAudit()
    return MultiCurrencyAgent(
        account_manager=AccountManager(account_store, ledger_store, audit),
        balance_engine=BalanceEngine(account_store, ledger_store),
        nostro_reconciler=NostroReconciler(nostro_store, audit),
        currency_router=CurrencyRouter(),
        conversion_tracker=ConversionTracker(conversion_store, ledger_store, audit),
    )


# ── create_multi_currency_account ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_account_returns_dict() -> None:
    agent = _make_agent()
    result = await agent.create_multi_currency_account("ent-001", "GBP", ["EUR"])
    assert "account_id" in result
    assert result["entity_id"] == "ent-001"
    assert result["base_currency"] == "GBP"


@pytest.mark.asyncio
async def test_create_account_contains_currencies() -> None:
    agent = _make_agent()
    result = await agent.create_multi_currency_account("ent-001", "GBP", ["EUR", "USD"])
    assert "GBP" in result["currencies"]
    assert "EUR" in result["currencies"]


# ── get_account_balances ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_account_balances_returns_currency_dict() -> None:
    agent = _make_agent()
    acct = await agent.create_multi_currency_account("ent-001", "GBP", ["EUR"])
    balances = await agent.get_account_balances(acct["account_id"])
    assert "GBP" in balances
    assert "EUR" in balances


@pytest.mark.asyncio
async def test_get_account_balances_values_are_strings() -> None:
    agent = _make_agent()
    acct = await agent.create_multi_currency_account("ent-001", "GBP", [])
    balances = await agent.get_account_balances(acct["account_id"])
    for value in balances.values():
        assert isinstance(value, str)


# ── convert_currency ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_convert_currency_debits_and_credits() -> None:
    agent = _make_agent()
    acct = await agent.create_multi_currency_account("ent-001", "GBP", ["EUR"])
    account_id = acct["account_id"]

    # Fund the GBP balance first
    await agent._balance_engine.credit(account_id, "GBP", Decimal("500"), "seed")

    result = await agent.convert_currency(account_id, "GBP", "EUR", "100", "1.16")
    assert result["from_currency"] == "GBP"
    assert result["to_currency"] == "EUR"
    assert result["status"] == "COMPLETED"


@pytest.mark.asyncio
async def test_convert_currency_fee_in_result() -> None:
    agent = _make_agent()
    acct = await agent.create_multi_currency_account("ent-001", "GBP", ["EUR"])
    account_id = acct["account_id"]
    await agent._balance_engine.credit(account_id, "GBP", Decimal("1000"), "seed")

    result = await agent.convert_currency(account_id, "GBP", "EUR", "500", "1.16")
    expected_fee = str(Decimal("500") * Decimal("0.002"))
    assert result["fee"] == expected_fee


@pytest.mark.asyncio
async def test_convert_currency_updates_balances() -> None:
    agent = _make_agent()
    acct = await agent.create_multi_currency_account("ent-001", "GBP", ["EUR"])
    account_id = acct["account_id"]
    await agent._balance_engine.credit(account_id, "GBP", Decimal("500"), "seed")

    await agent.convert_currency(account_id, "GBP", "EUR", "100", "1.16")
    balances = await agent.get_account_balances(account_id)
    assert Decimal(balances["GBP"]) == Decimal("400")
    assert Decimal(balances["EUR"]) == Decimal("116")


@pytest.mark.asyncio
async def test_convert_currency_insufficient_balance_raises() -> None:
    agent = _make_agent()
    acct = await agent.create_multi_currency_account("ent-001", "GBP", ["EUR"])
    with pytest.raises(ValueError, match="Insufficient balance"):
        await agent.convert_currency(acct["account_id"], "GBP", "EUR", "100", "1.16")


# ── reconcile_nostro ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reconcile_nostro_returns_dict() -> None:
    agent = _make_agent()
    result = await agent.reconcile_nostro("nostro-gbp-001", "5000000")
    assert "nostro_id" in result
    assert "status" in result
    assert result["status"] == "MATCHED"


@pytest.mark.asyncio
async def test_reconcile_nostro_discrepancy() -> None:
    agent = _make_agent()
    result = await agent.reconcile_nostro("nostro-gbp-001", "4000000")
    assert result["status"] == "DISCREPANCY"


@pytest.mark.asyncio
async def test_reconcile_nostro_amounts_are_strings() -> None:
    agent = _make_agent()
    result = await agent.reconcile_nostro("nostro-gbp-001", "5000000")
    assert isinstance(result["our_balance"], str)
    assert isinstance(result["their_balance"], str)
    assert isinstance(result["variance"], str)


# ── get_currency_report ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_currency_report_returns_consolidated_balance() -> None:
    agent = _make_agent()
    acct = await agent.create_multi_currency_account("ent-001", "GBP", ["EUR"])
    account_id = acct["account_id"]
    await agent._balance_engine.credit(account_id, "GBP", Decimal("1000"), "seed")
    await agent._balance_engine.credit(account_id, "EUR", Decimal("500"), "seed")

    report = await agent.get_currency_report(account_id, {"EUR": "0.85"})
    assert "consolidated_balance" in report
    consolidated = Decimal(report["consolidated_balance"])
    expected = Decimal("1000") + Decimal("500") * Decimal("0.85")
    assert consolidated == expected


@pytest.mark.asyncio
async def test_get_currency_report_breakdown_present() -> None:
    agent = _make_agent()
    acct = await agent.create_multi_currency_account("ent-001", "GBP", ["EUR"])
    account_id = acct["account_id"]

    report = await agent.get_currency_report(account_id, {"EUR": "0.85"})
    assert "breakdown" in report
    assert "GBP" in report["breakdown"]
    assert "EUR" in report["breakdown"]
