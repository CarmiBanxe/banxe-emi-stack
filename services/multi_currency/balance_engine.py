"""
services/multi_currency/balance_engine.py — Balance credit/debit and consolidation engine.

Phase 22 | IL-MCL-01 | banxe-emi-stack

Invariants:
  - I-01: All monetary amounts are Decimal — never float.
  - I-24: Every balance mutation creates an append-only LedgerEntry.
  - Debit raises ValueError("Insufficient balance") if available < amount.
  - Consolidated balance raises ValueError if FX rate missing for non-base currency.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from decimal import Decimal
import uuid

from services.multi_currency.models import (
    AccountStorePort,
    CurrencyBalance,
    LedgerEntry,
    LedgerEntryPort,
    MultiCurrencyAccount,
)


class BalanceEngine:
    """Handles credit, debit, and consolidated balance calculations."""

    def __init__(
        self,
        account_store: AccountStorePort,
        ledger_store: LedgerEntryPort,
    ) -> None:
        self._accounts = account_store
        self._ledger = ledger_store

    async def get_balance(self, account_id: str, currency: str) -> CurrencyBalance | None:
        """Return the CurrencyBalance for a specific currency, or None."""
        account = await self._accounts.get(account_id)
        if account is None:
            return None
        for bal in account.balances:
            if bal.currency == currency:
                return bal
        return None

    async def get_all_balances(self, account_id: str) -> list[CurrencyBalance]:
        """Return all CurrencyBalance objects for the account."""
        account = await self._accounts.get(account_id)
        if account is None:
            return []
        return list(account.balances)

    async def credit(
        self,
        account_id: str,
        currency: str,
        amount: Decimal,
        description: str,
    ) -> LedgerEntry:
        """Credit amount to currency balance and create an append-only LedgerEntry.

        Raises:
            ValueError: if account not found or currency not in account.
        """
        account = await self._accounts.get(account_id)
        if account is None:
            raise ValueError(f"Account not found: {account_id}")
        updated_account = _update_balance(account, currency, amount, "CREDIT")
        await self._accounts.save(updated_account)
        entry = LedgerEntry(
            entry_id=uuid.uuid4().hex,
            account_id=account_id,
            currency=currency,
            amount=amount,
            direction="CREDIT",
            description=description,
            created_at=datetime.now(UTC),
        )
        await self._ledger.append(entry)
        return entry

    async def debit(
        self,
        account_id: str,
        currency: str,
        amount: Decimal,
        description: str,
    ) -> LedgerEntry:
        """Debit amount from currency balance and create an append-only LedgerEntry.

        Raises:
            ValueError: if account not found, currency not in account, or
                        available balance < amount (Insufficient balance).
        """
        account = await self._accounts.get(account_id)
        if account is None:
            raise ValueError(f"Account not found: {account_id}")
        bal = _find_balance(account, currency)
        if bal.available < amount:
            raise ValueError("Insufficient balance")
        updated_account = _update_balance(account, currency, amount, "DEBIT")
        await self._accounts.save(updated_account)
        entry = LedgerEntry(
            entry_id=uuid.uuid4().hex,
            account_id=account_id,
            currency=currency,
            amount=amount,
            direction="DEBIT",
            description=description,
            created_at=datetime.now(UTC),
        )
        await self._ledger.append(entry)
        return entry

    async def get_consolidated_balance(
        self,
        account_id: str,
        rates: dict[str, Decimal],
    ) -> Decimal:
        """Sum all currency balances converted to the account's base_currency.

        Args:
            rates: dict mapping currency code → rate-to-base-currency.
                   Base currency itself is not required in this dict.

        Raises:
            ValueError: if account not found or a rate is missing for a non-base currency.
        """
        account = await self._accounts.get(account_id)
        if account is None:
            raise ValueError(f"Account not found: {account_id}")
        total = Decimal("0")
        for bal in account.balances:
            if bal.currency == account.base_currency:
                total += bal.amount
            else:
                if bal.currency not in rates:
                    raise ValueError(
                        f"Missing FX rate for {bal.currency} → {account.base_currency}"
                    )
                total += bal.amount * rates[bal.currency]
        return total

    async def get_ledger_entries(
        self,
        account_id: str,
        currency: str | None = None,
    ) -> list[LedgerEntry]:
        """Return ledger entries for an account, optionally filtered by currency."""
        return await self._ledger.list_entries(account_id, currency)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _find_balance(account: MultiCurrencyAccount, currency: str) -> CurrencyBalance:
    for bal in account.balances:
        if bal.currency == currency:
            return bal
    raise ValueError(f"Currency {currency} not in account {account.account_id}")


def _update_balance(
    account: MultiCurrencyAccount,
    currency: str,
    amount: Decimal,
    direction: str,
) -> MultiCurrencyAccount:
    """Return a new frozen account with the specified balance updated."""
    new_balances = []
    found = False
    for bal in account.balances:
        if bal.currency == currency:
            found = True
            if direction == "CREDIT":
                new_bal = dataclasses.replace(
                    bal,
                    amount=bal.amount + amount,
                    available=bal.available + amount,
                )
            else:  # DEBIT
                new_bal = dataclasses.replace(
                    bal,
                    amount=bal.amount - amount,
                    available=bal.available - amount,
                )
            new_balances.append(new_bal)
        else:
            new_balances.append(bal)
    if not found:
        raise ValueError(f"Currency {currency} not in account {account.account_id}")
    return dataclasses.replace(account, balances=tuple(new_balances))
