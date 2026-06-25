"""
services/ledger/ledger_port.py
LedgerPort Protocol for General Ledger operations (IL-FIN-01).

Hexagonal port: adapters interact with Midaz GL / InMemory stub.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from services.ledger.ledger_models import Account, JournalEntry


class LedgerInfrastructureError(RuntimeError):
    """Ledger backend is unreachable / returned a server error.

    Raised so an infrastructure failure SURFACES (fail-closed) instead of being
    silently masked as a zero balance / empty result. Distinct from a genuine
    "not found" or "no balance" answer from a reachable backend (which stays
    ``None`` / ``Decimal("0")`` / ``[]``). Consumers (e.g. reconciliation) must
    treat this as fail-closed — never as a real ``0`` tie-out.
    """


class LedgerPort(Protocol):
    """Port for General Ledger operations."""

    def create_account(self, account: Account) -> Account:
        """Create a new GL account."""
        ...

    def get_account(self, account_id: str) -> Account | None:
        """Fetch account by ID."""
        ...

    def post_journal_entry(self, entry: JournalEntry) -> JournalEntry:
        """Post a journal entry to the GL."""
        ...

    def get_journal_entry(self, entry_id: str) -> JournalEntry | None:
        """Fetch a journal entry by ID."""
        ...

    def get_account_balance(self, account_id: str) -> Decimal:
        """Return current balance for account (Decimal, I-01)."""
        ...
