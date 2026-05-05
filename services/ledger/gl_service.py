"""
services/ledger/gl_service.py
GLService — double-entry bookkeeping service (IL-FIN-01).

Covers S16 (Financial Accounts) and GAP D-gl (Midaz GL).

I-01: Decimal ONLY for money.
I-02: Blocked jurisdictions → account rejected.
I-04: High-value postings flagged for MLRO.
I-24: Immutable audit trail for every GL operation.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import uuid4

from services.ledger.ledger_models import (
    BLOCKED_JURISDICTIONS,
    HIGH_VALUE_THRESHOLD,
    SUPPORTED_CURRENCIES,
    Account,
    AccountType,
    GLAuditEntry,
    JournalEntry,
    Posting,
    PostingDirection,
    PostingStatus,
)
from services.ledger.ledger_port import LedgerPort

# ── Errors ───────────────────────────────────────────────────────────────────


class JurisdictionBlockedError(ValueError):
    """Raised when account jurisdiction is sanctioned (I-02)."""


class UnbalancedEntryError(ValueError):
    """Raised when journal entry debits != credits."""


class HighValuePostingError(ValueError):
    """Raised when posting exceeds high-value threshold without approval (I-04)."""


# ── Audit Port ───────────────────────────────────────────────────────────────


class GLAuditPort(Protocol):
    """Port for recording GL audit entries (I-24)."""

    def record(self, entry: GLAuditEntry) -> None: ...


class InMemoryGLAuditPort:
    """In-memory audit trail for tests."""

    def __init__(self) -> None:
        self._entries: list[GLAuditEntry] = []

    def record(self, entry: GLAuditEntry) -> None:
        self._entries.append(entry)

    @property
    def entries(self) -> list[GLAuditEntry]:
        return list(self._entries)


# ── HITL Proposal ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class HighValueHITLProposal:
    """High-value posting requires MLRO approval (I-04, I-27)."""

    entry_id: str
    total_amount: str  # Decimal as string
    currency: str
    reason: str
    requires_approval_from: str = "MLRO"


# ── GL Service ───────────────────────────────────────────────────────────────


class GLService:
    """
    General Ledger service with double-entry bookkeeping.

    Enforces:
    - Double-entry balance (debits == credits per currency)
    - Jurisdiction blocking (I-02)
    - High-value flagging (I-04)
    - Immutable audit trail (I-24)
    """

    def __init__(
        self,
        ledger: LedgerPort,
        audit: GLAuditPort | None = None,
    ) -> None:
        self._ledger = ledger
        self._audit: GLAuditPort = audit or InMemoryGLAuditPort()

    # ── Account Operations ───────────────────────────────────────────────────

    def create_account(
        self,
        name: str,
        account_type: AccountType,
        currency: str,
        jurisdiction: str = "GB",
    ) -> Account:
        """Create a new GL account. Rejects blocked jurisdictions (I-02)."""
        # I-02: block sanctioned jurisdictions.
        if jurisdiction.upper() in BLOCKED_JURISDICTIONS:
            raise JurisdictionBlockedError(
                f"Account jurisdiction {jurisdiction!r} is sanctioned (I-02)."
            )

        if currency not in SUPPORTED_CURRENCIES:
            raise ValueError(
                f"Unsupported currency: {currency} "
                f"(supported: {', '.join(sorted(SUPPORTED_CURRENCIES))})"
            )

        account = Account(
            account_id=f"acc-{uuid4().hex[:12]}",
            name=name,
            account_type=account_type,
            currency=currency,
            jurisdiction=jurisdiction.upper(),
        )
        created = self._ledger.create_account(account)

        self._record_audit(
            entry_id=created.account_id,
            action="CREATE_ACCOUNT",
            status=PostingStatus.POSTED,
            total_amount=Decimal("0"),
            currency=currency,
            actor="SYSTEM",
            details=f"type={account_type.value}, jurisdiction={jurisdiction.upper()}",
        )

        return created

    def get_account(self, account_id: str) -> Account | None:
        """Fetch account by ID."""
        return self._ledger.get_account(account_id)

    def get_balance(self, account_id: str) -> Decimal:
        """Return current balance for account (I-01: Decimal)."""
        return self._ledger.get_account_balance(account_id)

    # ── Journal Entry Operations ─────────────────────────────────────────────

    def post_journal_entry(
        self,
        description: str,
        postings: list[tuple[str, PostingDirection, Decimal, str]],
        high_value_approved: bool = False,
    ) -> JournalEntry | HighValueHITLProposal:
        """
        Post a double-entry journal entry.

        Each posting tuple: (account_id, direction, amount, currency).

        Returns JournalEntry if posted.
        Returns HighValueHITLProposal if total > threshold and not approved (I-04).
        Raises UnbalancedEntryError if debits != credits.
        """
        entry_id = f"je-{uuid4().hex[:12]}"

        # Build Posting objects.
        posting_objs: list[Posting] = []
        for i, (acc_id, direction, amount, currency) in enumerate(postings):
            if not isinstance(amount, Decimal):
                raise TypeError(f"Amount must be Decimal, got {type(amount).__name__} (I-01)")
            posting_objs.append(
                Posting(
                    posting_id=f"{entry_id}-p{i}",
                    account_id=acc_id,
                    direction=direction,
                    amount=amount,
                    currency=currency,
                )
            )

        # Validate double-entry balance per currency.
        self._validate_balance(posting_objs)

        # I-04: check high-value threshold.
        total_debit = sum(
            (p.amount for p in posting_objs if p.direction == PostingDirection.DEBIT),
            Decimal("0"),
        )
        currencies = {p.currency for p in posting_objs}
        primary_currency = next(iter(currencies))

        if total_debit >= HIGH_VALUE_THRESHOLD and not high_value_approved:
            return HighValueHITLProposal(
                entry_id=entry_id,
                total_amount=str(total_debit),
                currency=primary_currency,
                reason=(
                    f"Journal entry total {primary_currency} {total_debit} "
                    f"exceeds high-value threshold {HIGH_VALUE_THRESHOLD}. "
                    "MLRO approval required (I-04, I-27)."
                ),
            )

        entry = JournalEntry(
            entry_id=entry_id,
            description=description,
            postings=tuple(posting_objs),
        )

        posted = self._ledger.post_journal_entry(entry)

        self._record_audit(
            entry_id=entry_id,
            action="POST_JOURNAL_ENTRY",
            status=posted.status,
            total_amount=total_debit,
            currency=primary_currency,
            actor="SYSTEM",
            details=f"postings={len(posting_objs)}, description={description}",
        )

        return posted

    # ── Private helpers ──────────────────────────────────────────────────────

    def _validate_balance(self, postings: list[Posting]) -> None:
        """Validate that debits == credits per currency."""
        # Group by currency.
        by_currency: dict[str, dict[str, Decimal]] = {}
        for p in postings:
            if p.currency not in by_currency:
                by_currency[p.currency] = {"DEBIT": Decimal("0"), "CREDIT": Decimal("0")}
            by_currency[p.currency][p.direction.value] += p.amount

        for currency, totals in by_currency.items():
            if totals["DEBIT"] != totals["CREDIT"]:
                raise UnbalancedEntryError(
                    f"Unbalanced entry for {currency}: "
                    f"debits={totals['DEBIT']}, credits={totals['CREDIT']}. "
                    "Double-entry requires debits == credits."
                )

    def _record_audit(
        self,
        *,
        entry_id: str,
        action: str,
        status: PostingStatus,
        total_amount: Decimal,
        currency: str,
        actor: str,
        details: str = "",
    ) -> None:
        entry = GLAuditEntry(
            entry_id=entry_id,
            action=action,
            status=status,
            total_amount=total_amount,
            currency=currency,
            actor=actor,
            details=details,
        )
        self._audit.record(entry)
