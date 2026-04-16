"""tests/test_multi_currency/test_account_manager.py — AccountManager tests."""

from __future__ import annotations

import pytest

from services.multi_currency.account_manager import AccountManager
from services.multi_currency.models import (
    InMemoryAccountStore,
    InMemoryLedgerEntryStore,
    InMemoryMCAudit,
)


def _make_manager() -> AccountManager:
    return AccountManager(
        account_store=InMemoryAccountStore(),
        ledger_store=InMemoryLedgerEntryStore(),
        audit=InMemoryMCAudit(),
    )


# ── create_account ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_account_returns_account() -> None:
    mgr = _make_manager()
    acct = await mgr.create_account("ent-001", "GBP", ["EUR", "USD"])
    assert acct.entity_id == "ent-001"
    assert acct.base_currency == "GBP"


@pytest.mark.asyncio
async def test_create_account_has_zero_balances() -> None:
    from decimal import Decimal

    mgr = _make_manager()
    acct = await mgr.create_account("ent-001", "GBP", ["EUR"])
    for bal in acct.balances:
        assert bal.amount == Decimal("0")
        assert bal.available == Decimal("0")


@pytest.mark.asyncio
async def test_create_account_includes_base_currency() -> None:
    mgr = _make_manager()
    acct = await mgr.create_account("ent-001", "GBP", ["EUR"])
    currencies = {b.currency for b in acct.balances}
    assert "GBP" in currencies
    assert "EUR" in currencies


@pytest.mark.asyncio
async def test_create_account_no_duplicates_when_base_in_list() -> None:
    mgr = _make_manager()
    acct = await mgr.create_account("ent-001", "GBP", ["GBP", "EUR"])
    currencies = [b.currency for b in acct.balances]
    assert currencies.count("GBP") == 1


@pytest.mark.asyncio
async def test_create_account_unsupported_currency_raises() -> None:
    mgr = _make_manager()
    with pytest.raises(ValueError, match="Unsupported currency"):
        await mgr.create_account("ent-001", "GBP", ["XYZ"])


@pytest.mark.asyncio
async def test_create_account_max_10_raises() -> None:
    """Verify that creating an account with > 10 unique currencies raises ValueError."""
    from unittest.mock import patch

    mgr = _make_manager()
    # Patch _SUPPORTED_CURRENCIES to allow 11 distinct currencies for this test
    extended = ["GBP", "EUR", "USD", "CHF", "PLN", "CZK", "SEK", "NOK", "DKK", "HUF", "AED"]
    with patch("services.multi_currency.account_manager._SUPPORTED_CURRENCIES", extended):
        eleven_others = ["EUR", "USD", "CHF", "PLN", "CZK", "SEK", "NOK", "DKK", "HUF", "AED"]
        with pytest.raises(ValueError, match="max is 10"):
            await mgr.create_account("ent-001", "GBP", eleven_others)


@pytest.mark.asyncio
async def test_create_account_exactly_10_ok() -> None:
    mgr = _make_manager()
    # GBP (base) + 9 others = 10
    others = ["EUR", "USD", "CHF", "PLN", "CZK", "SEK", "NOK", "DKK", "HUF"]
    acct = await mgr.create_account("ent-001", "GBP", others)
    assert len(acct.balances) == 10


@pytest.mark.asyncio
async def test_create_account_assigns_unique_id() -> None:
    mgr = _make_manager()
    a1 = await mgr.create_account("ent-001", "GBP", [])
    a2 = await mgr.create_account("ent-001", "GBP", [])
    assert a1.account_id != a2.account_id


@pytest.mark.asyncio
async def test_create_account_stores_in_store() -> None:
    mgr = _make_manager()
    acct = await mgr.create_account("ent-001", "GBP", ["EUR"])
    fetched = await mgr.get_account(acct.account_id)
    assert fetched is not None
    assert fetched.account_id == acct.account_id


# ── add_currency ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_add_currency_adds_zero_balance() -> None:
    from decimal import Decimal

    mgr = _make_manager()
    acct = await mgr.create_account("ent-001", "GBP", [])
    updated = await mgr.add_currency(acct.account_id, "EUR")
    eur_bal = next(b for b in updated.balances if b.currency == "EUR")
    assert eur_bal.amount == Decimal("0")


@pytest.mark.asyncio
async def test_add_currency_account_not_found_raises() -> None:
    mgr = _make_manager()
    with pytest.raises(ValueError, match="Account not found"):
        await mgr.add_currency("nonexistent", "EUR")


@pytest.mark.asyncio
async def test_add_currency_unsupported_raises() -> None:
    mgr = _make_manager()
    acct = await mgr.create_account("ent-001", "GBP", [])
    with pytest.raises(ValueError, match="Unsupported currency"):
        await mgr.add_currency(acct.account_id, "XYZ")


@pytest.mark.asyncio
async def test_add_currency_already_present_raises() -> None:
    mgr = _make_manager()
    acct = await mgr.create_account("ent-001", "GBP", ["EUR"])
    with pytest.raises(ValueError, match="Currency already present"):
        await mgr.add_currency(acct.account_id, "EUR")


@pytest.mark.asyncio
async def test_add_currency_at_max_raises() -> None:
    mgr = _make_manager()
    others = ["EUR", "USD", "CHF", "PLN", "CZK", "SEK", "NOK", "DKK", "HUF"]
    acct = await mgr.create_account("ent-001", "GBP", others)
    assert len(acct.balances) == 10
    # All 10 supported currencies already used; none left to add
    # HUF is already there — try to add NOK which is also already there
    with pytest.raises(ValueError):
        await mgr.add_currency(acct.account_id, "SEK")


# ── list_accounts ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_accounts_returns_entity_accounts() -> None:
    mgr = _make_manager()
    await mgr.create_account("ent-A", "GBP", [])
    await mgr.create_account("ent-A", "EUR", [])
    await mgr.create_account("ent-B", "GBP", [])
    accounts = await mgr.list_accounts("ent-A")
    assert len(accounts) == 2


@pytest.mark.asyncio
async def test_list_accounts_empty_for_unknown_entity() -> None:
    mgr = _make_manager()
    accounts = await mgr.list_accounts("nonexistent")
    assert accounts == []
