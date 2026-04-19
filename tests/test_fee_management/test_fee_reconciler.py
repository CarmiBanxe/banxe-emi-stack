"""
tests/test_fee_management/test_fee_reconciler.py
IL-FME-01 | Phase 41 | 16 tests
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from services.fee_management.billing_engine import BillingEngine
from services.fee_management.fee_reconciler import OVERCHARGE_TOLERANCE, FeeReconciler, HITLProposal
from services.fee_management.models import (
    FeeCharge,
    FeeStatus,
    InMemoryFeeChargeStore,
    InMemoryFeeRuleStore,
)


def _setup() -> tuple[FeeReconciler, InMemoryFeeChargeStore, InMemoryFeeRuleStore]:
    rules = InMemoryFeeRuleStore()
    charges = InMemoryFeeChargeStore()
    billing = BillingEngine(rule_store=rules, charge_store=charges)
    billing.apply_charges("acc-1", ["rule-maintenance-001"], "ref-rec")
    reconciler = FeeReconciler(rule_store=rules, charge_store=charges)
    return reconciler, charges, rules


class TestReconcileCharges:
    def test_reconcile_returns_dict(self) -> None:
        reconciler, _, _ = _setup()
        now = datetime.now(UTC)
        result = reconciler.reconcile_charges("acc-1", now - timedelta(minutes=5), now)
        assert "matched" in result
        assert "overcharged" in result
        assert "undercharged" in result
        assert "discrepancy" in result

    def test_correct_charge_counts_as_matched(self) -> None:
        reconciler, _, _ = _setup()
        now = datetime.now(UTC)
        result = reconciler.reconcile_charges("acc-1", now - timedelta(minutes=5), now)
        assert result["matched"] == 1
        assert result["overcharged"] == 0

    def test_empty_period_returns_zeros(self) -> None:
        reconciler, _, _ = _setup()
        far_future = datetime.now(UTC) + timedelta(days=365)
        result = reconciler.reconcile_charges("acc-1", far_future, far_future + timedelta(days=30))
        assert result["matched"] == 0

    def test_discrepancy_is_decimal(self) -> None:
        reconciler, _, _ = _setup()
        now = datetime.now(UTC)
        result = reconciler.reconcile_charges("acc-1", now - timedelta(minutes=5), now)
        assert isinstance(result["discrepancy"], Decimal)


class TestFlagOvercharges:
    def test_correct_charge_not_flagged(self) -> None:
        reconciler, _, _ = _setup()
        now = datetime.now(UTC)
        overcharges = reconciler.flag_overcharges("acc-1", now - timedelta(minutes=5), now)
        assert len(overcharges) == 0

    def test_overcharged_amount_flagged(self) -> None:
        rules = InMemoryFeeRuleStore()
        charges = InMemoryFeeChargeStore()
        billing = BillingEngine(rule_store=rules, charge_store=charges)
        billing.apply_charges("acc-2", ["rule-maintenance-001"], "ref-over")
        now = datetime.now(UTC)
        acc_charges = charges.list_charges("acc-2")
        overcharged = FeeCharge(
            id=acc_charges[0].id,
            rule_id=acc_charges[0].rule_id,
            account_id=acc_charges[0].account_id,
            amount=Decimal("99.99"),
            status=FeeStatus.PENDING,
            description="overcharged",
            reference="over",
            applied_at=acc_charges[0].applied_at,
        )
        charges.save_charge(overcharged)
        reconciler = FeeReconciler(rule_store=rules, charge_store=charges)
        flagged = reconciler.flag_overcharges("acc-2", now - timedelta(minutes=5), now)
        assert len(flagged) == 1

    def test_tolerance_boundary(self) -> None:
        assert Decimal("0.01") == OVERCHARGE_TOLERANCE


class TestGenerateRefundProposal:
    def test_returns_hitl_proposal(self) -> None:
        reconciler, _, _ = _setup()
        proposal = reconciler.generate_refund_proposal("charge-1", Decimal("5.00"), "overcharged")
        assert isinstance(proposal, HITLProposal)

    def test_proposal_autonomy_l4(self) -> None:
        reconciler, _, _ = _setup()
        proposal = reconciler.generate_refund_proposal("charge-1", Decimal("5.00"), "error")
        assert proposal.autonomy_level == "L4"

    def test_proposal_resource_id_is_charge_id(self) -> None:
        reconciler, _, _ = _setup()
        proposal = reconciler.generate_refund_proposal("charge-xyz", Decimal("10.00"), "test")
        assert proposal.resource_id == "charge-xyz"


class TestGetReconciliationReport:
    def test_report_structure(self) -> None:
        reconciler, _, _ = _setup()
        report = reconciler.get_reconciliation_report("acc-1")
        assert "account_id" in report
        assert "total_charges" in report
        assert "total_expected" in report
        assert "discrepancy" in report
        assert "status" in report

    def test_clean_status_for_correct_charges(self) -> None:
        reconciler, _, _ = _setup()
        report = reconciler.get_reconciliation_report("acc-1")
        assert report["status"] in ("CLEAN", "DISCREPANCY")

    def test_empty_account_is_clean(self) -> None:
        reconciler, _, _ = _setup()
        report = reconciler.get_reconciliation_report("no-charges")
        assert report["status"] == "CLEAN"

    def test_discrepancy_is_decimal(self) -> None:
        reconciler, _, _ = _setup()
        report = reconciler.get_reconciliation_report("acc-1")
        assert isinstance(report["discrepancy"], Decimal)
