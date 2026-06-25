"""
tests/test_high_value_approval.py — high-value approval audit (D-gl DoD #5).

A posting >= HIGH_VALUE_THRESHOLD (£50k) is never auto-posted (I-04): it is
staged + recorded PENDING. A named human must approve (which posts it) or reject
(which does not) — I-27, no auto-approve. The approval store is append-only
(I-24). All offline; Decimal-only (I-01).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.ledger.approval_models import ApprovalDecision
from services.ledger.gl_service import GLService, HighValueHITLProposal
from services.ledger.inmemory_ledger import InMemoryLedger
from services.ledger.ledger_models import AccountType, PostingDirection


def _service() -> GLService:
    svc = GLService(ledger=InMemoryLedger())
    svc.create_account("Ops", AccountType.ASSET, "GBP")
    svc.create_account("Liab", AccountType.LIABILITY, "GBP")
    return svc


def _accounts(svc: GLService) -> tuple[str, str]:
    ids = list(svc._ledger.accounts.keys())  # type: ignore[attr-defined]
    return ids[0], ids[1]


def _high_value_postings(a: str, b: str):
    amt = Decimal("60000.00")  # >= £50k threshold
    return [
        (a, PostingDirection.DEBIT, amt, "GBP"),
        (b, PostingDirection.CREDIT, amt, "GBP"),
    ]


def test_high_value_proposal_recorded_pending():
    svc = _service()
    a, b = _accounts(svc)
    result = svc.post_journal_entry("big", _high_value_postings(a, b))
    assert isinstance(result, HighValueHITLProposal)
    # not posted yet
    assert svc.get_balance(a) == Decimal("0")
    # PENDING approval row recorded (I-24)
    rec = svc.approval_store.get(result.entry_id)
    assert rec is not None
    assert rec.decision == ApprovalDecision.PENDING
    assert rec.total_amount == Decimal("60000.00")  # Decimal (I-01)


def test_approve_requires_human_approver():
    svc = _service()
    a, b = _accounts(svc)
    proposal = svc.post_journal_entry("big", _high_value_postings(a, b))
    for blank in ("", "   "):
        with pytest.raises(ValueError, match="named human approver"):
            svc.approve_high_value(proposal.entry_id, blank)


def test_approve_posts_entry_and_records_approved():
    svc = _service()
    a, b = _accounts(svc)
    proposal = svc.post_journal_entry("big", _high_value_postings(a, b))
    posted = svc.approve_high_value(proposal.entry_id, "mlro-alice", "verified")
    assert posted.entry_id == proposal.entry_id
    assert svc.get_balance(a) == Decimal("60000.00")  # now posted
    rec = svc.approval_store.get(proposal.entry_id)
    assert rec.decision == ApprovalDecision.APPROVED
    assert rec.approver == "mlro-alice"


def test_reject_does_not_post():
    svc = _service()
    a, b = _accounts(svc)
    proposal = svc.post_journal_entry("big", _high_value_postings(a, b))
    rejection = svc.reject_high_value(proposal.entry_id, "mlro-bob", "suspicious")
    assert rejection.decision == ApprovalDecision.REJECTED
    assert svc.get_balance(a) == Decimal("0")  # never posted


def test_reject_requires_human_approver():
    svc = _service()
    a, b = _accounts(svc)
    proposal = svc.post_journal_entry("big", _high_value_postings(a, b))
    with pytest.raises(ValueError, match="named human approver"):
        svc.reject_high_value(proposal.entry_id, "")


def test_approval_store_append_only():
    svc = _service()
    a, b = _accounts(svc)
    proposal = svc.post_journal_entry("big", _high_value_postings(a, b))
    svc.approve_high_value(proposal.entry_id, "mlro-alice")
    rows = [r for r in svc.approval_store.records if r.proposal_id == proposal.entry_id]
    # PENDING row retained + APPROVED row appended (never mutated in place)
    assert [r.decision for r in rows] == [ApprovalDecision.PENDING, ApprovalDecision.APPROVED]


def test_approve_unknown_raises():
    svc = _service()
    with pytest.raises(ValueError, match="No pending high-value"):
        svc.approve_high_value("je-nope", "mlro-alice")


def test_below_threshold_posts_directly_no_approval():
    svc = _service()
    a, b = _accounts(svc)
    amt = Decimal("100.00")
    result = svc.post_journal_entry(
        "small",
        [(a, PostingDirection.DEBIT, amt, "GBP"), (b, PostingDirection.CREDIT, amt, "GBP")],
    )
    assert not isinstance(result, HighValueHITLProposal)
    assert svc.get_balance(a) == Decimal("100.00")
