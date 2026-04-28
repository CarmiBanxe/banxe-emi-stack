"""
services/ledger/payment_posting_service.py
PaymentPostingService — wires payment events to GL journal entries (IL-CBS-01).

When a payment settles/refunds, auto-posts balanced double-entry journal entries.
I-01: Decimal ONLY.
I-02: Blocked jurisdictions → reject.
I-04: High-value flagged.
I-24: Immutable audit trail.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from services.ledger.gl_service import GLService, HighValueHITLProposal
from services.ledger.ledger_models import (
    JournalEntry,
    PostingDirection,
)
from services.ledger.posting_models import PaymentEvent
from services.ledger.posting_rules import (
    HighValuePostingFlag,
    PostingRuleEngine,
)

# ── Audit ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PostingAuditEntry:
    """Immutable audit entry for payment postings (I-24)."""

    event_id: str
    transaction_id: str
    event_type: str
    journal_entry_id: str | None
    amount: Decimal  # I-01
    currency: str
    action: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    details: str = ""


class PostingAuditPort(Protocol):
    """Port for recording posting audit entries (I-24)."""

    def record(self, entry: PostingAuditEntry) -> None: ...


class InMemoryPostingAuditPort:
    """In-memory audit for tests."""

    def __init__(self) -> None:
        self._entries: list[PostingAuditEntry] = []

    def record(self, entry: PostingAuditEntry) -> None:
        self._entries.append(entry)

    @property
    def entries(self) -> list[PostingAuditEntry]:
        return list(self._entries)


# ── Account Registry ─────────────────────────────────────────────────────────


class AccountRegistry:
    """
    Maps logical account types to GL account IDs.

    In production, backed by database lookup.
    For tests, uses in-memory mapping.
    """

    def __init__(self) -> None:
        self._accounts: dict[str, dict[str, str]] = {}

    def register(self, account_type: str, currency: str, account_id: str) -> None:
        key = f"{account_type}:{currency}"
        self._accounts[key] = {"account_id": account_id, "currency": currency}

    def get_account_id(self, account_type: str, currency: str) -> str | None:
        key = f"{account_type}:{currency}"
        entry = self._accounts.get(key)
        return entry["account_id"] if entry else None


# ── Payment Posting Service ──────────────────────────────────────────────────


class PaymentPostingService:
    """
    Processes payment events into GL journal entries.

    For each payment event (capture, settle, refund):
    1. Resolve posting rule (debit/credit account types)
    2. Map account types to GL account IDs
    3. Post balanced double-entry journal entry
    4. Record audit trail

    I-01: Decimal amounts.
    I-02: Blocked jurisdictions rejected.
    I-04: High-value events flagged.
    I-24: Immutable audit trail.
    """

    def __init__(
        self,
        gl: GLService,
        rules: PostingRuleEngine | None = None,
        registry: AccountRegistry | None = None,
        audit: PostingAuditPort | None = None,
    ) -> None:
        self._gl = gl
        self._rules = rules or PostingRuleEngine()
        self._registry = registry or AccountRegistry()
        self._audit: PostingAuditPort = audit or InMemoryPostingAuditPort()
        self._high_value_flags: list[HighValuePostingFlag] = []

    @property
    def high_value_flags(self) -> list[HighValuePostingFlag]:
        return list(self._high_value_flags)

    def process_event(
        self,
        event: PaymentEvent,
        high_value_approved: bool = False,
    ) -> JournalEntry | HighValueHITLProposal:
        """
        Process a payment event into a GL journal entry.

        Returns JournalEntry if posted.
        Returns HighValueHITLProposal if high-value and not approved (I-04).
        Raises JurisdictionBlockedError for blocked jurisdictions (I-02).
        """
        # Resolve posting rule (checks I-02).
        rule = self._rules.resolve(event)

        # Check high value (I-04).
        hv_flag = self._rules.check_high_value(event)
        if hv_flag is not None:
            self._high_value_flags.append(hv_flag)

        # Resolve account IDs.
        debit_acc = self._registry.get_account_id(rule.debit_account_type, event.currency)
        credit_acc = self._registry.get_account_id(rule.credit_account_type, event.currency)

        if debit_acc is None or credit_acc is None:
            raise ValueError(
                f"Account not found for posting: debit={rule.debit_account_type}, "
                f"credit={rule.credit_account_type}, currency={event.currency}"
            )

        description = self._rules.get_description(rule, event)

        # Post journal entry via GLService.
        result = self._gl.post_journal_entry(
            description=description,
            postings=[
                (debit_acc, PostingDirection.DEBIT, event.amount, event.currency),
                (credit_acc, PostingDirection.CREDIT, event.amount, event.currency),
            ],
            high_value_approved=high_value_approved,
        )

        # Determine journal entry ID for audit.
        je_id = result.entry_id if isinstance(result, JournalEntry) else None

        # I-24: audit trail.
        self._audit.record(
            PostingAuditEntry(
                event_id=event.event_id,
                transaction_id=event.transaction_id,
                event_type=event.event_type.value,
                journal_entry_id=je_id,
                amount=event.amount,
                currency=event.currency,
                action="POST_PAYMENT_EVENT",
                details=f"debit={rule.debit_account_type}, credit={rule.credit_account_type}",
            )
        )

        return result

    def get_gl_balance(self, account_type: str, currency: str) -> Decimal:
        """Get GL balance for a logical account type (I-01)."""
        acc_id = self._registry.get_account_id(account_type, currency)
        if acc_id is None:
            raise ValueError(f"Account not found: {account_type}:{currency}")
        return self._gl.get_balance(acc_id)
