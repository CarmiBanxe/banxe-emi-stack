"""
tests/test_fee_management/test_waiver_manager.py
IL-FME-01 | Phase 41 | 16 tests
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.fee_management.billing_engine import BillingEngine
from services.fee_management.models import (
    FeeStatus,
    InMemoryFeeChargeStore,
    InMemoryFeeRuleStore,
    InMemoryFeeWaiverStore,
    WaiverReason,
)
from services.fee_management.waiver_manager import HITLProposal, WaiverManager


def _setup() -> tuple[WaiverManager, InMemoryFeeChargeStore, str]:
    rule_store = InMemoryFeeRuleStore()
    charge_store = InMemoryFeeChargeStore()
    waiver_store = InMemoryFeeWaiverStore()
    billing = BillingEngine(rule_store=rule_store, charge_store=charge_store)
    charges = billing.apply_charges("acc-1", ["rule-maintenance-001"], "ref-001")
    charge_id = charges[0].id
    manager = WaiverManager(charge_store=charge_store, waiver_store=waiver_store)
    return manager, charge_store, charge_id


class TestRequestWaiver:
    def test_request_returns_hitl_proposal(self) -> None:
        manager, _, charge_id = _setup()
        proposal = manager.request_waiver(charge_id, "acc-1", WaiverReason.GOODWILL, "user-1")
        assert isinstance(proposal, HITLProposal)

    def test_hitl_proposal_autonomy_level_l4(self) -> None:
        manager, _, charge_id = _setup()
        proposal = manager.request_waiver(charge_id, "acc-1", WaiverReason.GOODWILL, "user-1")
        assert proposal.autonomy_level == "L4"

    def test_hitl_proposal_action(self) -> None:
        manager, _, charge_id = _setup()
        proposal = manager.request_waiver(charge_id, "acc-1", WaiverReason.PROMOTION, "user-1")
        assert "approve" in proposal.action.lower() or "waiver" in proposal.action.lower()

    def test_request_creates_pending_waiver(self) -> None:
        manager, _, charge_id = _setup()
        manager.request_waiver(charge_id, "acc-1", WaiverReason.GOODWILL, "user-1")
        active = manager.list_active_waivers("acc-1")
        assert len(active) == 1
        assert active[0].status == "PENDING"


class TestApproveWaiver:
    def test_approve_sets_approved_status(self) -> None:
        manager, _, charge_id = _setup()
        proposal = manager.request_waiver(charge_id, "acc-1", WaiverReason.GOODWILL, "user-1")
        waiver = manager.approve_waiver(proposal.resource_id, "compliance-officer")
        assert waiver.status == "APPROVED"

    def test_approve_sets_approved_by(self) -> None:
        manager, _, charge_id = _setup()
        proposal = manager.request_waiver(charge_id, "acc-1", WaiverReason.GOODWILL, "user-1")
        waiver = manager.approve_waiver(proposal.resource_id, "compliance-officer")
        assert waiver.approved_by == "compliance-officer"

    def test_approve_sets_resolved_at(self) -> None:
        manager, _, charge_id = _setup()
        proposal = manager.request_waiver(charge_id, "acc-1", WaiverReason.GOODWILL, "user-1")
        waiver = manager.approve_waiver(proposal.resource_id, "compliance-officer")
        assert waiver.resolved_at is not None

    def test_approve_marks_charge_as_waived(self) -> None:
        manager, charge_store, charge_id = _setup()
        proposal = manager.request_waiver(charge_id, "acc-1", WaiverReason.GOODWILL, "user-1")
        manager.approve_waiver(proposal.resource_id, "compliance-officer")
        charge = charge_store.get_charge(charge_id)
        assert charge is not None
        assert charge.status == FeeStatus.WAIVED

    def test_approve_unknown_waiver_raises(self) -> None:
        manager, _, _ = _setup()
        with pytest.raises(ValueError):
            manager.approve_waiver("nonexistent-waiver", "officer")


class TestRejectWaiver:
    def test_reject_sets_rejected_status(self) -> None:
        manager, _, charge_id = _setup()
        proposal = manager.request_waiver(charge_id, "acc-1", WaiverReason.GOODWILL, "user-1")
        waiver = manager.reject_waiver(proposal.resource_id, "compliance-officer")
        assert waiver.status == "REJECTED"

    def test_reject_unknown_raises(self) -> None:
        manager, _, _ = _setup()
        with pytest.raises(ValueError):
            manager.reject_waiver("bad-id", "officer")


class TestListActiveWaivers:
    def test_pending_in_active(self) -> None:
        manager, _, charge_id = _setup()
        manager.request_waiver(charge_id, "acc-1", WaiverReason.GOODWILL, "user-1")
        active = manager.list_active_waivers("acc-1")
        assert any(w.status == "PENDING" for w in active)

    def test_rejected_not_in_active(self) -> None:
        manager, _, charge_id = _setup()
        proposal = manager.request_waiver(charge_id, "acc-1", WaiverReason.GOODWILL, "user-1")
        manager.reject_waiver(proposal.resource_id, "officer")
        active = manager.list_active_waivers("acc-1")
        assert all(w.status != "REJECTED" for w in active)


class TestCheckWaiverEligibility:
    def test_goodwill_always_eligible(self) -> None:
        manager, _, _ = _setup()
        result = manager.check_waiver_eligibility("acc-1", WaiverReason.GOODWILL)
        assert result["eligible"] is True

    def test_promotion_eligible_if_few_recent(self) -> None:
        manager, _, _ = _setup()
        result = manager.check_waiver_eligibility("acc-new", WaiverReason.PROMOTION)
        assert result["eligible"] is True

    def test_max_waiver_is_decimal(self) -> None:
        manager, _, _ = _setup()
        result = manager.check_waiver_eligibility("acc-1", WaiverReason.GOODWILL)
        assert isinstance(result["max_waiver"], Decimal)
