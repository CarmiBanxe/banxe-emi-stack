"""
tests/test_fee_management/test_billing_engine.py
IL-FME-01 | Phase 41 | 16 tests
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from services.fee_management.billing_engine import BillingEngine
from services.fee_management.models import (
    BillingCycle,
    FeeStatus,
    InMemoryFeeChargeStore,
    InMemoryFeeRuleStore,
)


def _engine() -> tuple[BillingEngine, InMemoryFeeChargeStore, InMemoryFeeRuleStore]:
    rules = InMemoryFeeRuleStore()
    charges = InMemoryFeeChargeStore()
    engine = BillingEngine(rule_store=rules, charge_store=charges)
    return engine, charges, rules


class TestGenerateInvoice:
    def test_empty_invoice_returns_zero_totals(self) -> None:
        engine, _, _ = _engine()
        now = datetime.now(UTC)
        summary = engine.generate_invoice(
            "acc-x", BillingCycle.MONTHLY, now - timedelta(days=30), now
        )
        assert summary.total_charged == Decimal("0.00")
        assert summary.total_waived == Decimal("0.00")
        assert summary.outstanding == Decimal("0.00")

    def test_invoice_sums_charges_in_period(self) -> None:
        engine, _, rules = _engine()
        engine.apply_charges("acc-1", ["rule-swift-001"], "ref-001")
        now = datetime.now(UTC)
        summary = engine.generate_invoice(
            "acc-1", BillingCycle.MONTHLY, now - timedelta(minutes=1), now
        )
        assert summary.total_charged > Decimal("0")

    def test_invoice_excludes_out_of_period(self) -> None:
        engine, _, _ = _engine()
        engine.apply_charges("acc-1", ["rule-swift-001"], "ref-001")
        future_start = datetime.now(UTC) + timedelta(days=1)
        future_end = datetime.now(UTC) + timedelta(days=30)
        summary = engine.generate_invoice("acc-1", BillingCycle.MONTHLY, future_start, future_end)
        assert summary.total_charged == Decimal("0.00")

    def test_invoice_account_id_correct(self) -> None:
        engine, _, _ = _engine()
        now = datetime.now(UTC)
        summary = engine.generate_invoice("acc-test", BillingCycle.MONTHLY, now, now)
        assert summary.account_id == "acc-test"


class TestApplyCharges:
    def test_apply_creates_pending_charges(self) -> None:
        engine, charges, _ = _engine()
        result = engine.apply_charges("acc-1", ["rule-maintenance-001"], "ref-001")
        assert len(result) == 1
        assert result[0].status == FeeStatus.PENDING

    def test_apply_multiple_rules(self) -> None:
        engine, charges, _ = _engine()
        result = engine.apply_charges(
            "acc-1", ["rule-maintenance-001", "rule-swift-001"], "ref-002"
        )
        assert len(result) == 2

    def test_apply_unknown_rule_skipped(self) -> None:
        engine, _, _ = _engine()
        result = engine.apply_charges("acc-1", ["non-existent-rule"], "ref-003")
        assert result == []

    def test_applied_charge_has_correct_amount(self) -> None:
        engine, _, _ = _engine()
        result = engine.apply_charges("acc-1", ["rule-maintenance-001"], "ref-004")
        assert result[0].amount == Decimal("4.99")


class TestOutstanding:
    def test_pending_charges_in_outstanding(self) -> None:
        engine, _, _ = _engine()
        engine.apply_charges("acc-1", ["rule-maintenance-001"], "ref-out")
        outstanding = engine.get_outstanding("acc-1")
        assert len(outstanding) == 1
        assert all(c.status == FeeStatus.PENDING for c in outstanding)

    def test_paid_charge_not_in_outstanding(self) -> None:
        engine, _, _ = _engine()
        charges = engine.apply_charges("acc-1", ["rule-maintenance-001"], "ref-paid")
        engine.mark_paid(charges[0].id)
        outstanding = engine.get_outstanding("acc-1")
        assert all(c.id != charges[0].id for c in outstanding)


class TestMarkPaid:
    def test_mark_paid_sets_status_applied(self) -> None:
        engine, _, _ = _engine()
        charges = engine.apply_charges("acc-2", ["rule-atm-withdrawal-001"], "ref-mp")
        updated = engine.mark_paid(charges[0].id)
        assert updated.status == FeeStatus.APPLIED

    def test_mark_paid_sets_paid_at(self) -> None:
        engine, _, _ = _engine()
        charges = engine.apply_charges("acc-2", ["rule-atm-withdrawal-001"], "ref-mp2")
        updated = engine.mark_paid(charges[0].id)
        assert updated.paid_at is not None

    def test_mark_paid_unknown_raises(self) -> None:
        engine, _, _ = _engine()
        with pytest.raises(ValueError):
            engine.mark_paid("nonexistent-charge-id")


class TestBillingHistory:
    def test_history_returns_most_recent_first(self) -> None:
        engine, _, _ = _engine()
        engine.apply_charges("acc-3", ["rule-maintenance-001"], "ref-h1")
        engine.apply_charges("acc-3", ["rule-swift-001"], "ref-h2")
        history = engine.get_billing_history("acc-3", limit=10)
        assert len(history) == 2
        assert history[0].applied_at >= history[1].applied_at

    def test_history_respects_limit(self) -> None:
        engine, _, _ = _engine()
        for i in range(5):
            engine.apply_charges("acc-4", ["rule-maintenance-001"], f"ref-{i}")
        history = engine.get_billing_history("acc-4", limit=3)
        assert len(history) == 3
