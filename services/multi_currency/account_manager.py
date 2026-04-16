"""
services/multi_currency/account_manager.py — Multi-currency account creation and management.

Phase 22 | IL-MCL-01 | banxe-emi-stack

Invariants:
  - I-01: All monetary amounts are Decimal — never float.
  - max_currencies = 10 per account (hard limit enforced here).
  - New accounts always start with zero balances.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from decimal import Decimal
import uuid

from services.multi_currency.models import (
    _SUPPORTED_CURRENCIES,
    AccountStorePort,
    CurrencyBalance,
    LedgerEntryPort,
    MCAuditPort,
    MCEventEntry,
    MultiCurrencyAccount,
)


class AccountManager:
    """Creates and manages multi-currency accounts for EMI entities."""

    def __init__(
        self,
        account_store: AccountStorePort,
        ledger_store: LedgerEntryPort,
        audit: MCAuditPort,
    ) -> None:
        self._accounts = account_store
        self._ledger = ledger_store
        self._audit = audit

    async def create_account(
        self,
        entity_id: str,
        base_currency: str,
        initial_currencies: list[str],
    ) -> MultiCurrencyAccount:
        """Create a new multi-currency account with zero balances.

        Raises:
            ValueError: if any currency is unsupported or more than 10 requested.
        """
        all_currencies = list(dict.fromkeys([base_currency, *initial_currencies]))
        if len(all_currencies) > 10:
            raise ValueError(
                f"Cannot create account with {len(all_currencies)} currencies; max is 10."
            )
        for ccy in all_currencies:
            if ccy not in _SUPPORTED_CURRENCIES:
                raise ValueError(f"Unsupported currency: {ccy}")

        balances = tuple(
            CurrencyBalance(
                currency=ccy,
                amount=Decimal("0"),
                available=Decimal("0"),
                reserved=Decimal("0"),
            )
            for ccy in all_currencies
        )
        account = MultiCurrencyAccount(
            account_id=f"mc-{uuid.uuid4().hex[:12]}",
            entity_id=entity_id,
            base_currency=base_currency,
            balances=balances,
            created_at=datetime.now(UTC),
        )
        await self._accounts.save(account)
        await self._audit.log(
            MCEventEntry(
                event_id=uuid.uuid4().hex,
                account_id=account.account_id,
                event_type="ACCOUNT_CREATED",
                currency=base_currency,
                amount=Decimal("0"),
                created_at=datetime.now(UTC),
            )
        )
        return account

    async def add_currency(
        self,
        account_id: str,
        currency: str,
    ) -> MultiCurrencyAccount:
        """Add a new currency (zero balance) to an existing account.

        Raises:
            ValueError: if account not found, currency unsupported, already present,
                        or account is already at max 10 currencies.
        """
        account = await self._accounts.get(account_id)
        if account is None:
            raise ValueError(f"Account not found: {account_id}")
        if currency not in _SUPPORTED_CURRENCIES:
            raise ValueError(f"Unsupported currency: {currency}")
        existing = {b.currency for b in account.balances}
        if currency in existing:
            raise ValueError(f"Currency already present: {currency}")
        if len(account.balances) >= account.max_currencies:
            raise ValueError(
                f"Account {account_id} already has {account.max_currencies} currencies (max)."
            )
        new_balance = CurrencyBalance(
            currency=currency,
            amount=Decimal("0"),
            available=Decimal("0"),
            reserved=Decimal("0"),
        )
        updated = dataclasses.replace(
            account,
            balances=(*account.balances, new_balance),
        )
        await self._accounts.save(updated)
        await self._audit.log(
            MCEventEntry(
                event_id=uuid.uuid4().hex,
                account_id=account_id,
                event_type="CURRENCY_ADDED",
                currency=currency,
                amount=Decimal("0"),
                created_at=datetime.now(UTC),
            )
        )
        return updated

    async def get_account(self, account_id: str) -> MultiCurrencyAccount | None:
        """Fetch account by ID, returns None if not found."""
        return await self._accounts.get(account_id)

    async def list_accounts(self, entity_id: str) -> list[MultiCurrencyAccount]:
        """List all accounts for a given entity."""
        return await self._accounts.list_by_entity(entity_id)
