"""
services/ledger/ledger_models.py
General Ledger domain models (IL-FIN-01).

Double-entry bookkeeping: every JournalEntry has balanced debit/credit postings.

I-01: All monetary values are Decimal — never float.
I-24: Immutable records via frozen dataclasses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum


class PostingStatus(str, Enum):
    """Status of a journal entry posting.

    Lifecycle (mirrors Midaz, additive over the legacy PENDING/POSTED/REVERSED/
    FAILED): a staged entry is PENDING, then COMMITTED (counts toward balance)
    or CANCELLED (voided, no balance impact). A POSTED/COMMITTED entry may be
    REVERSED (dropped from balance, with a lineage reversing entry). NOTED marks
    an annotation record — records-only, never a balance impact. The legacy
    immediate ``post_journal_entry`` path still uses POSTED (also counts).
    """

    PENDING = "PENDING"
    POSTED = "POSTED"
    COMMITTED = "COMMITTED"
    CANCELLED = "CANCELLED"
    REVERSED = "REVERSED"
    NOTED = "NOTED"
    FAILED = "FAILED"


# Statuses that contribute to an account balance (POSTED = legacy immediate
# post; COMMITTED = committed lifecycle entry). PENDING/CANCELLED/REVERSED/
# NOTED/FAILED are excluded.
BALANCE_AFFECTING_STATUSES: frozenset[PostingStatus] = frozenset(
    {PostingStatus.POSTED, PostingStatus.COMMITTED}
)


class AccountType(str, Enum):
    """Chart of accounts classification."""

    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    EQUITY = "EQUITY"
    REVENUE = "REVENUE"
    EXPENSE = "EXPENSE"


class PostingDirection(str, Enum):
    """Debit or credit."""

    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


SUPPORTED_CURRENCIES: frozenset[str] = frozenset({"GBP", "EUR", "USD"})

BLOCKED_JURISDICTIONS: frozenset[str] = frozenset(
    {
        "RU",
        "BY",
        "IR",
        "KP",
        "CU",
        "MM",
        "AF",
        "VE",
        "SY",
    }
)

# I-04: high-value posting threshold.
HIGH_VALUE_THRESHOLD: Decimal = Decimal("50000")


@dataclass(frozen=True)
class Account:
    """A General Ledger account (I-24 immutable)."""

    account_id: str
    name: str
    account_type: AccountType
    currency: str
    jurisdiction: str = "GB"
    is_active: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def __post_init__(self) -> None:
        if self.currency not in SUPPORTED_CURRENCIES:
            raise ValueError(
                f"Unsupported currency: {self.currency} "
                f"(supported: {', '.join(sorted(SUPPORTED_CURRENCIES))})"
            )


@dataclass(frozen=True)
class Posting:
    """A single debit or credit within a journal entry (I-24 immutable)."""

    posting_id: str
    account_id: str
    direction: PostingDirection
    amount: Decimal  # I-01
    currency: str

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            raise TypeError(f"amount must be Decimal, got {type(self.amount).__name__} (I-01)")
        if self.amount <= Decimal("0"):
            raise ValueError(f"amount must be positive, got {self.amount}")
        if self.currency not in SUPPORTED_CURRENCIES:
            raise ValueError(f"Unsupported currency: {self.currency}")


@dataclass(frozen=True)
class JournalEntry:
    """
    A double-entry journal entry (I-24 immutable).

    Invariant: sum of debits == sum of credits for the same currency.
    """

    entry_id: str
    description: str
    postings: tuple[Posting, ...]
    status: PostingStatus = PostingStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if len(self.postings) < 2:
            raise ValueError("Journal entry must have at least 2 postings")


@dataclass(frozen=True)
class GLAuditEntry:
    """Immutable audit record for GL operations (I-24)."""

    entry_id: str
    action: str
    status: PostingStatus
    total_amount: Decimal  # I-01
    currency: str
    actor: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    details: str = ""
