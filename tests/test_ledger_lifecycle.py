"""
tests/test_ledger_lifecycle.py — GL transaction lifecycle (D-gl build-spec DoD #4).

`test_transaction_lifecycle`: create -> commit (PENDING -> COMMITTED, counts);
cancel a PENDING (no balance impact); revert a POSTED/COMMITTED entry (nets the
balance back, with a lineage reversing entry); annotation = records-only, never
a balance impact. Legacy immediate `post_journal_entry` (POSTED) still counts —
backward compatible. All offline; Decimal-only (I-01).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.ledger.gl_service import GLService, InMemoryGLAuditPort
from services.ledger.inmemory_ledger import InMemoryLedger
from services.ledger.ledger_models import (
    Account,
    AccountType,
    JournalEntry,
    Posting,
    PostingDirection,
    PostingStatus,
)

A = "acct-asset"
B = "acct-liability"


def _ledger() -> InMemoryLedger:
    led = InMemoryLedger()
    led.create_account(
        Account(account_id=A, name="Asset", account_type=AccountType.ASSET, currency="GBP")
    )
    led.create_account(
        Account(account_id=B, name="Liab", account_type=AccountType.LIABILITY, currency="GBP")
    )
    return led


def _entry(entry_id: str, amount: str = "100.00") -> JournalEntry:
    return JournalEntry(
        entry_id=entry_id,
        description="test",
        postings=(
            Posting(f"{entry_id}-d", A, PostingDirection.DEBIT, Decimal(amount), "GBP"),
            Posting(f"{entry_id}-c", B, PostingDirection.CREDIT, Decimal(amount), "GBP"),
        ),
    )


# ── create -> commit ──────────────────────────────────────────────────────────


def test_create_stages_pending_not_counted():
    led = _ledger()
    staged = led.create_journal_entry(_entry("e1"))
    assert staged.status == PostingStatus.PENDING
    assert led.get_account_balance(A) == Decimal("0")  # PENDING not counted


def test_commit_pending_to_committed_counts():
    led = _ledger()
    led.create_journal_entry(_entry("e1"))
    committed = led.commit_journal_entry("e1")
    assert committed.status == PostingStatus.COMMITTED
    assert led.get_account_balance(A) == Decimal("100.00")  # COMMITTED counts


def test_commit_non_pending_raises():
    led = _ledger()
    led.post_journal_entry(_entry("e1"))  # POSTED, not PENDING
    with pytest.raises(ValueError, match="Cannot commit"):
        led.commit_journal_entry("e1")


def test_commit_unknown_raises():
    led = _ledger()
    with pytest.raises(ValueError, match="unknown"):
        led.commit_journal_entry("nope")


# ── cancel ──────────────────────────────────────────────────────────────────


def test_cancel_pending_no_balance_impact():
    led = _ledger()
    led.create_journal_entry(_entry("e1"))
    cancelled = led.cancel_journal_entry("e1")
    assert cancelled.status == PostingStatus.CANCELLED
    assert led.get_account_balance(A) == Decimal("0")


def test_cancel_committed_raises():
    led = _ledger()
    led.create_journal_entry(_entry("e1"))
    led.commit_journal_entry("e1")
    with pytest.raises(ValueError, match="Cannot cancel"):
        led.cancel_journal_entry("e1")


# ── revert ────────────────────────────────────────────────────────────────────


def test_revert_posted_nets_balance_to_zero():
    led = _ledger()
    led.post_journal_entry(_entry("e1"))  # POSTED, +100
    assert led.get_account_balance(A) == Decimal("100.00")
    reversing = led.revert_journal_entry("e1")
    assert reversing.entry_id == "e1-rev"
    assert reversing.metadata["reverses"] == "e1"
    assert led.get_journal_entry("e1").status == PostingStatus.REVERSED
    assert reversing.status == PostingStatus.REVERSED
    assert led.get_account_balance(A) == Decimal("0")  # no double-count


def test_revert_committed_nets_balance_to_zero():
    led = _ledger()
    led.create_journal_entry(_entry("e1"))
    led.commit_journal_entry("e1")
    assert led.get_account_balance(A) == Decimal("100.00")
    led.revert_journal_entry("e1")
    assert led.get_account_balance(A) == Decimal("0")


def test_revert_pending_raises():
    led = _ledger()
    led.create_journal_entry(_entry("e1"))  # PENDING — not revertible
    with pytest.raises(ValueError, match="Cannot revert"):
        led.revert_journal_entry("e1")


def test_revert_unknown_raises():
    led = _ledger()
    with pytest.raises(ValueError, match="unknown"):
        led.revert_journal_entry("nope")


# ── annotate ──────────────────────────────────────────────────────────────────


def test_annotate_noted_no_balance_impact():
    led = _ledger()
    led.post_journal_entry(_entry("e1"))
    before = led.get_account_balance(A)
    annotation = led.annotate_journal_entry("e1", "reviewed by ops")
    assert annotation.status == PostingStatus.NOTED
    assert annotation.details == "reviewed by ops"
    assert led.get_account_balance(A) == before  # unchanged
    assert led.annotations and led.annotations[0].entry_id == "e1"


def test_annotate_unknown_raises():
    led = _ledger()
    with pytest.raises(ValueError, match="unknown"):
        led.annotate_journal_entry("nope", "x")


# ── backward compatibility ────────────────────────────────────────────────────


def test_legacy_posted_still_counts():
    led = _ledger()
    led.post_journal_entry(_entry("e1"))  # legacy immediate POSTED
    assert led.get_journal_entry("e1").status == PostingStatus.POSTED
    assert led.get_account_balance(A) == Decimal("100.00")


# ── GLService wrappers record audit (I-24) ────────────────────────────────────


def test_gl_service_lifecycle_records_audit():
    led = _ledger()
    audit = InMemoryGLAuditPort()
    svc = GLService(ledger=led, audit=audit)

    led.create_journal_entry(_entry("e1"))
    svc.commit_entry("e1", actor="ops")
    svc.annotate_entry("e1", "note")
    svc.revert_entry("e1", actor="ops")

    actions = [a.action for a in audit.entries]
    assert "COMMIT_JOURNAL_ENTRY" in actions
    assert "ANNOTATE" in actions
    assert "REVERT_JOURNAL_ENTRY" in actions
    # commit counted, then revert netted back to zero
    assert led.get_account_balance(A) == Decimal("0")
