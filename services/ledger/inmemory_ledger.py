"""
services/ledger/inmemory_ledger.py
InMemoryLedger — test stub implementing LedgerPort (IL-FIN-01).

I-01: All monetary values are Decimal.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

from services.ledger.ledger_models import (
    BALANCE_AFFECTING_STATUSES,
    Account,
    GLAuditEntry,
    JournalEntry,
    Posting,
    PostingDirection,
    PostingStatus,
)


class InMemoryLedger:
    """In-memory GL implementing LedgerPort for unit tests."""

    def __init__(self) -> None:
        self._accounts: dict[str, Account] = {}
        self._entries: dict[str, JournalEntry] = {}
        self._annotations: list[GLAuditEntry] = []

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
                raise ValueError(f"Account {posting.account_id!r} not found for posting")
        posted = replace(entry, status=PostingStatus.POSTED)
        self._entries[entry.entry_id] = posted
        return posted

    def get_journal_entry(self, entry_id: str) -> JournalEntry | None:
        return self._entries.get(entry_id)

    def get_account_balance(self, account_id: str) -> Decimal:
        """Compute balance from balance-affecting entries (POSTED + COMMITTED).

        PENDING / CANCELLED / REVERSED / NOTED / FAILED entries are excluded
        (I-01: Decimal).
        """
        if account_id not in self._accounts:
            raise ValueError(f"Account {account_id!r} not found")
        balance = Decimal("0")
        for entry in self._entries.values():
            if entry.status not in BALANCE_AFFECTING_STATUSES:
                continue
            for posting in entry.postings:
                if posting.account_id == account_id:
                    if posting.direction == PostingDirection.DEBIT:
                        balance += posting.amount
                    else:
                        balance -= posting.amount
        return balance

    # ── transaction lifecycle (mirrors Midaz; additive over post_journal_entry) ──

    def create_journal_entry(self, entry: JournalEntry) -> JournalEntry:
        """Stage a balanced entry as PENDING (not yet counted toward balance)."""
        if entry.entry_id in self._entries:
            raise ValueError(f"Journal entry {entry.entry_id!r} already exists")
        for posting in entry.postings:
            if posting.account_id not in self._accounts:
                raise ValueError(f"Account {posting.account_id!r} not found for posting")
        pending = replace(entry, status=PostingStatus.PENDING)
        self._entries[entry.entry_id] = pending
        return pending

    def commit_journal_entry(self, entry_id: str) -> JournalEntry:
        """PENDING -> COMMITTED (now counts toward balance)."""
        committed = replace(
            self._require_status(entry_id, "commit", PostingStatus.PENDING),
            status=PostingStatus.COMMITTED,
        )
        self._entries[entry_id] = committed
        return committed

    def cancel_journal_entry(self, entry_id: str) -> JournalEntry:
        """PENDING -> CANCELLED (voided, no balance impact)."""
        cancelled = replace(
            self._require_status(entry_id, "cancel", PostingStatus.PENDING),
            status=PostingStatus.CANCELLED,
        )
        self._entries[entry_id] = cancelled
        return cancelled

    def revert_journal_entry(self, entry_id: str) -> JournalEntry:
        """Revert a POSTED/COMMITTED entry.

        The original flips to REVERSED (dropped from balance). A lineage
        reversing entry (postings with directions swapped) is recorded — also
        REVERSED, so it never re-adds to a balance. Net effect: the original
        entry's contribution is removed exactly once (no double-count).
        """
        original = self._require_status(
            entry_id, "revert", PostingStatus.POSTED, PostingStatus.COMMITTED
        )
        self._entries[entry_id] = replace(original, status=PostingStatus.REVERSED)

        reversing = JournalEntry(
            entry_id=f"{entry_id}-rev",
            description=f"Reversal of {entry_id}",
            postings=tuple(self._swap(p) for p in original.postings),
            status=PostingStatus.REVERSED,
            metadata={**original.metadata, "reverses": entry_id},
        )
        self._entries[reversing.entry_id] = reversing
        return reversing

    def annotate_journal_entry(self, entry_id: str, note: str) -> GLAuditEntry:
        """Attach a records-only NOTED annotation (never a balance impact)."""
        entry = self._entries.get(entry_id)
        if entry is None:
            raise ValueError(f"Cannot annotate unknown journal entry {entry_id!r}")
        annotation = GLAuditEntry(
            entry_id=entry_id,
            action="ANNOTATE",
            status=PostingStatus.NOTED,
            total_amount=Decimal("0"),
            currency=entry.postings[0].currency,
            actor="system",
            timestamp=datetime.now(UTC).isoformat(),
            details=note,
        )
        self._annotations.append(annotation)
        return annotation

    # ── helpers ──────────────────────────────────────────────────────────────

    def _require_status(self, entry_id: str, action: str, *allowed: PostingStatus) -> JournalEntry:
        entry = self._entries.get(entry_id)
        if entry is None:
            raise ValueError(f"Cannot {action} unknown journal entry {entry_id!r}")
        if entry.status not in allowed:
            allowed_names = "/".join(s.value for s in allowed)
            raise ValueError(
                f"Cannot {action} entry {entry_id!r} in status {entry.status.value} "
                f"(requires {allowed_names})"
            )
        return entry

    @staticmethod
    def _swap(posting: Posting) -> Posting:
        flipped = (
            PostingDirection.CREDIT
            if posting.direction == PostingDirection.DEBIT
            else PostingDirection.DEBIT
        )
        return replace(posting, posting_id=f"{posting.posting_id}-rev", direction=flipped)

    @property
    def annotations(self) -> list[GLAuditEntry]:
        return list(self._annotations)

    @property
    def accounts(self) -> dict[str, Account]:
        return dict(self._accounts)

    @property
    def entries(self) -> dict[str, JournalEntry]:
        return dict(self._entries)
