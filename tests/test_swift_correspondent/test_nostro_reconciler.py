"""
Tests for Nostro Reconciler.
IL-SWF-01 | Sprint 34 | Phase 47
Tests: tolerance Decimal (I-22), mismatch HITL (I-27), I-24 append-only
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.swift_correspondent.models import HITLProposal, InMemoryNostroStore
from services.swift_correspondent.nostro_reconciler import (
    RECON_TOLERANCE,
    NostroReconciler,
)


@pytest.fixture
def reconciler():
    return NostroReconciler(store=InMemoryNostroStore())


class TestTakeSnapshot:
    def test_snapshot_creates_position(self, reconciler):
        pos = reconciler.take_snapshot("cb_001", "EUR", Decimal("100000"), Decimal("100000"))
        assert pos.bank_id == "cb_001"
        assert pos.currency == "EUR"

    def test_snapshot_mismatch_calculated(self, reconciler):
        pos = reconciler.take_snapshot("cb_001", "EUR", Decimal("100000"), Decimal("99999"))
        assert pos.mismatch_amount == Decimal("1")

    def test_snapshot_zero_mismatch(self, reconciler):
        pos = reconciler.take_snapshot("cb_001", "EUR", Decimal("50000"), Decimal("50000"))
        assert pos.mismatch_amount == Decimal("0")

    def test_snapshot_amounts_are_decimal(self, reconciler):
        pos = reconciler.take_snapshot("cb_001", "GBP", Decimal("1000"), Decimal("1000"))
        assert isinstance(pos.our_balance, Decimal)
        assert isinstance(pos.their_balance, Decimal)
        assert isinstance(pos.mismatch_amount, Decimal)

    def test_snapshot_date_is_utc(self, reconciler):
        pos = reconciler.take_snapshot("cb_001", "EUR", Decimal("1000"), Decimal("1000"))
        assert pos.snapshot_date  # UTC timestamp present

    def test_snapshot_append_only_multiple(self, reconciler):
        reconciler.take_snapshot("cb_001", "EUR", Decimal("1000"), Decimal("1000"))
        reconciler.take_snapshot("cb_001", "EUR", Decimal("2000"), Decimal("2000"))
        # Second snapshot becomes latest
        store = InMemoryNostroStore()
        rec2 = NostroReconciler(store=store)
        rec2.take_snapshot("cb_001", "EUR", Decimal("1000"), Decimal("1000"))
        rec2.take_snapshot("cb_001", "EUR", Decimal("2000"), Decimal("2000"))
        latest = store.get_latest("cb_001", "EUR")
        assert latest.our_balance == Decimal("2000")


class TestCheckMismatch:
    def test_no_mismatch_below_tolerance(self, reconciler):
        reconciler.take_snapshot("cb_001", "GBP", Decimal("100000"), Decimal("100000"))
        has_mismatch, amount = reconciler.check_mismatch("cb_001", "GBP")
        assert has_mismatch is False
        assert amount == Decimal("0")

    def test_mismatch_above_tolerance(self, reconciler):
        reconciler.take_snapshot("cb_001", "GBP", Decimal("100000"), Decimal("99999"))
        has_mismatch, amount = reconciler.check_mismatch("cb_001", "GBP")
        assert has_mismatch is True
        assert amount == Decimal("1")

    def test_mismatch_at_tolerance_no_alert(self, reconciler):
        # Exactly at tolerance — not above
        reconciler.take_snapshot("cb_001", "GBP", Decimal("100000"), Decimal("99999.99"))
        has_mismatch, amount = reconciler.check_mismatch("cb_001", "GBP")
        assert has_mismatch is False  # 0.01 == tolerance, not > tolerance

    def test_no_position_returns_false(self, reconciler):
        has_mismatch, amount = reconciler.check_mismatch("cb_999", "EUR")
        assert has_mismatch is False
        assert amount == Decimal("0")


class TestReconcile:
    def test_reconcile_within_tolerance_returns_position(self, reconciler):
        result = reconciler.reconcile("cb_001", "EUR", Decimal("1000"), Decimal("1000"))
        from services.swift_correspondent.models import NostroPosition

        assert isinstance(result, NostroPosition)

    def test_reconcile_mismatch_returns_hitl_proposal(self, reconciler):
        result = reconciler.reconcile("cb_001", "EUR", Decimal("1000"), Decimal("500"))
        assert isinstance(result, HITLProposal)
        assert result.autonomy_level == "L4"
        assert result.requires_approval_from == "TREASURY_OPS"

    def test_reconcile_hitl_reason_contains_mismatch(self, reconciler):
        result = reconciler.reconcile("cb_001", "EUR", Decimal("10000"), Decimal("5000"))
        assert isinstance(result, HITLProposal)
        assert "mismatch" in result.reason.lower() or "5000" in result.reason

    def test_reconcile_mismatch_above_penny(self, reconciler):
        # Mismatch of £0.02 should trigger HITL
        result = reconciler.reconcile("cb_001", "GBP", Decimal("1000"), Decimal("999.98"))
        assert isinstance(result, HITLProposal)

    def test_reconcile_decimal_tolerance(self, reconciler):
        assert Decimal("0.01") == RECON_TOLERANCE


class TestGetDailyPositions:
    def test_daily_positions_empty(self, reconciler):
        positions = reconciler.get_daily_positions("cb_999")
        assert positions == []

    def test_daily_positions_after_snapshot(self, reconciler):
        reconciler.take_snapshot("cb_001", "EUR", Decimal("1000"), Decimal("1000"))
        positions = reconciler.get_daily_positions("cb_001")
        assert len(positions) >= 1


class TestReconciliationSummary:
    def test_summary_structure(self, reconciler):
        summary = reconciler.get_reconciliation_summary()
        assert "total_snapshots" in summary
        assert "mismatches" in summary
        assert "currencies" in summary

    def test_summary_counts_snapshots(self, reconciler):
        reconciler.take_snapshot("cb_001", "EUR", Decimal("1000"), Decimal("1000"))
        summary = reconciler.get_reconciliation_summary()
        assert summary["total_snapshots"] >= 1
