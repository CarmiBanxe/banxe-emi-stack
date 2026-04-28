"""
services/ledger/inmemory_ledger.py
InMemoryLedger — test stub implementing LedgerPort (IL-FIN-01).

I-01: All monetary values are Decimal.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from services.ledger.ledger_models import (
    Account,
    JournalEntry,
    PostingDirection,
    PostingStatus,
)


class InMemoryLedger:
    """In-memory GL implementing LedgerPort for unit tests."""

    def __init__(self) -> None:
        self._accounts: dict[str, Account] = {}
        self._entries: dict[str, JournalEntry] = {}

    def create_account(self, account: Account) -> Account:
        if account.account_id in self._accounts:
            raise ValueError(f"Account {account.account_id!r} already exists")
        self._accounts[account.account_id] = account
        return account

    def get_account(self, account_id: str) -> Account | None:
        return self._accounts.get(account_id)

    def post_journal_entry(self, entry: JournalEntry) -> JournalEntry:
        if entry.entry_id in self._entries:
            raise ValueError(f"Journal entry {entry.entry_id!r} already exists")
        # Verify all accounts exist.
        for posting in entry.postings:
            if posting.account_id not in self._accounts:
                raise ValueError(
                    f"Account {posting.account_id!r} not found for posting"
                )
        posted = replace(entry, status=PostingStatus.POSTED)
        self._entries[entry.entry_id] = posted
        return posted

    def get_journal_entry(self, entry_id: str) -> JournalEntry | None:
        return self._entries.get(entry_id)

    def get_account_balance(self, account_id: str) -> Decimal:
        """Compute balance from posted journal entries (I-01: Decimal)."""
        if account_id not in self._accounts:
            raise ValueError(f"Account {account_id!r} not found")
        balance = Decimal("0")
        for entry in self._entries.values():
            if entry.status != PostingStatus.POSTED:
                continue
            for posting in entry.postings:
                if posting.account_id == account_id:
                    if posting.direction == PostingDirection.DEBIT:
                        balance += posting.amount
                    else:
                        balance -= posting.amount
        return balance

    @property
    def accounts(self) -> dict[str, Account]:
        return dict(self._accounts)

    @property
    def entries(self) -> dict[str, JournalEntry]:
        return dict(self._entries)
