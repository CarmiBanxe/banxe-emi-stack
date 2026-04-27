"""
tests/test_lifecycle_kyc_integration.py
IL-KYC-01: Customer Lifecycle FSM × KYC/EDD pipeline integration tests.

6 acceptance-criteria tests:
  1. test_prospect_to_customer_requires_kyc_approved
  2. test_kyc_pending_blocks_activation_if_not_approved
  3. test_customer_restricted_on_edd_breach
  4. test_restricted_to_customer_requires_hitl
  5. test_closed_requires_fatca_crs_complete
  6. test_blocked_jurisdiction_customer_rejected
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.customer_lifecycle.fsm import (
    EddBreachError,
    FatcaCrsIncompleteError,
    HITLRequiredError,
    InMemoryFatcaCrsGuard,
    InMemoryHITLLifecyclePort,
    InMemoryKYCGuard,
    KYCLifecycleEngine,
    KYCNotApprovedError,
)
from services.customer_lifecycle.lifecycle_engine import InMemoryLifecycleStore, LifecycleEngine
from services.customer_lifecycle.lifecycle_models import CustomerState, LifecycleEvent
from services.kyc.kyc_port import KYCStatus


def _make_engine(
    kyc_guard: InMemoryKYCGuard | None = None,
    fatca_crs: InMemoryFatcaCrsGuard | None = None,
    hitl: InMemoryHITLLifecyclePort | None = None,
) -> KYCLifecycleEngine:
    base = LifecycleEngine(InMemoryLifecycleStore())
    return KYCLifecycleEngine(
        engine=base,
        kyc_guard=kyc_guard or InMemoryKYCGuard(),
        fatca_crs=fatca_crs or InMemoryFatcaCrsGuard(),
        hitl=hitl or InMemoryHITLLifecyclePort(),
    )


def _advance_to_kyc_pending(engine: KYCLifecycleEngine, cid: str) -> None:
    """Drive customer from PROSPECT to KYC_PENDING."""
    engine.transition(cid, LifecycleEvent.SUBMIT_APPLICATION)
    engine.transition(cid, LifecycleEvent.COMPLETE_KYC)
    assert engine.get_state(cid) == CustomerState.KYC_PENDING


def _advance_to_active(engine: KYCLifecycleEngine, cid: str) -> None:
    """Drive customer from PROSPECT to ACTIVE (KYC APPROVED)."""
    kyc_guard = InMemoryKYCGuard(default=KYCStatus.APPROVED)
    kyc_guard.set_status(cid, KYCStatus.APPROVED)
    # Re-use the engine's guard by setting it directly is not possible;
    # caller must pass an APPROVED guard to the engine.
    engine.transition(cid, LifecycleEvent.SUBMIT_APPLICATION)
    engine.transition(cid, LifecycleEvent.COMPLETE_KYC)
    engine.transition(cid, LifecycleEvent.ACTIVATE)
    assert engine.get_state(cid) == CustomerState.ACTIVE


# ── AC-1: prospect → customer requires KYC APPROVED ──────────────────────────


class TestProspectToCustomerRequiresKycApproved:
    def test_prospect_to_customer_requires_kyc_approved(self) -> None:
        """KYC_PENDING → ACTIVE blocked when KYC status is APPROVED."""
        kyc_guard = InMemoryKYCGuard(default=KYCStatus.APPROVED)
        engine = _make_engine(kyc_guard=kyc_guard)
        cid = "CUST-001"
        _advance_to_kyc_pending(engine, cid)
        kyc_guard.set_status(cid, KYCStatus.APPROVED)

        result = engine.transition(cid, LifecycleEvent.ACTIVATE)

        assert result is not None
        assert result.to_state == CustomerState.ACTIVE
        assert engine.get_state(cid) == CustomerState.ACTIVE


# ── AC-2: KYC_PENDING blocks activation if not approved ──────────────────────


class TestKycPendingBlocksActivation:
    def test_kyc_pending_blocks_activation_if_not_approved(self) -> None:
        """KYC_PENDING → ACTIVE raises KYCNotApprovedError when KYC not APPROVED."""
        kyc_guard = InMemoryKYCGuard(default=KYCStatus.PENDING)
        engine = _make_engine(kyc_guard=kyc_guard)
        cid = "CUST-002"
        _advance_to_kyc_pending(engine, cid)
        # KYC remains PENDING (not approved)

        with pytest.raises(KYCNotApprovedError, match="APPROVED required"):
            engine.transition(cid, LifecycleEvent.ACTIVATE)

        # State must not change
        assert engine.get_state(cid) == CustomerState.KYC_PENDING

    def test_kyc_rejected_also_blocks_activation(self) -> None:
        """KYCNotApprovedError raised when KYC is REJECTED."""
        kyc_guard = InMemoryKYCGuard(default=KYCStatus.REJECTED)
        engine = _make_engine(kyc_guard=kyc_guard)
        cid = "CUST-003"
        _advance_to_kyc_pending(engine, cid)

        with pytest.raises(KYCNotApprovedError):
            engine.transition(cid, LifecycleEvent.ACTIVATE)


# ── AC-3: customer restricted on EDD breach ───────────────────────────────────


class TestCustomerRestrictedOnEddBreach:
    def test_customer_restricted_on_edd_breach(self) -> None:
        """EDD breach (>£10k individual) suspends customer — EddBreachError raised (I-04)."""
        kyc_guard = InMemoryKYCGuard()
        cid = "CUST-004"
        kyc_guard.set_status(cid, KYCStatus.APPROVED)
        engine = _make_engine(kyc_guard=kyc_guard)

        engine.transition(cid, LifecycleEvent.SUBMIT_APPLICATION)
        engine.transition(cid, LifecycleEvent.COMPLETE_KYC)
        engine.transition(cid, LifecycleEvent.ACTIVATE)
        assert engine.get_state(cid) == CustomerState.ACTIVE

        # I-01: Decimal amount, I-04: £10,000 individual EDD trigger
        with pytest.raises(EddBreachError, match="EDD threshold breached"):
            engine.trigger_edd_restriction(cid, amount=Decimal("10000"), entity_type="INDIVIDUAL")

        assert engine.get_state(cid) == CustomerState.SUSPENDED

    def test_below_edd_threshold_does_not_restrict(self) -> None:
        """Amount below EDD threshold does not trigger suspension."""
        kyc_guard = InMemoryKYCGuard()
        cid = "CUST-005"
        kyc_guard.set_status(cid, KYCStatus.APPROVED)
        engine = _make_engine(kyc_guard=kyc_guard)

        engine.transition(cid, LifecycleEvent.SUBMIT_APPLICATION)
        engine.transition(cid, LifecycleEvent.COMPLETE_KYC)
        engine.transition(cid, LifecycleEvent.ACTIVATE)

        result = engine.trigger_edd_restriction(
            cid, amount=Decimal("9999.99"), entity_type="INDIVIDUAL"
        )

        assert result is None
        assert engine.get_state(cid) == CustomerState.ACTIVE


# ── AC-4: restricted → customer requires HITL L4 MLRO ────────────────────────


class TestRestrictedToCustomerRequiresHitl:
    def test_restricted_to_customer_requires_hitl(self) -> None:
        """SUSPENDED → ACTIVE requires MLRO L4 approval (I-27)."""
        kyc_guard = InMemoryKYCGuard()
        hitl = InMemoryHITLLifecyclePort()
        cid = "CUST-006"
        kyc_guard.set_status(cid, KYCStatus.APPROVED)
        engine = _make_engine(kyc_guard=kyc_guard, hitl=hitl)

        engine.transition(cid, LifecycleEvent.SUBMIT_APPLICATION)
        engine.transition(cid, LifecycleEvent.COMPLETE_KYC)
        engine.transition(cid, LifecycleEvent.ACTIVATE)
        engine.transition(cid, LifecycleEvent.SUSPEND)
        assert engine.get_state(cid) == CustomerState.SUSPENDED

        # Without approval → blocked
        with pytest.raises(HITLRequiredError, match="MLRO L4 approval"):
            engine.transition(cid, LifecycleEvent.ACTIVATE)

        # Grant MLRO approval → succeeds
        hitl.grant_approval(cid, "restricted_to_customer")
        result = engine.transition(cid, LifecycleEvent.ACTIVATE)
        assert result is not None
        assert engine.get_state(cid) == CustomerState.ACTIVE


# ── AC-5: closed requires FATCA/CRS complete ─────────────────────────────────


class TestClosedRequiresFatcaCrsComplete:
    def test_closed_requires_fatca_crs_complete(self) -> None:
        """CLOSE transition blocked when FATCA/CRS reporting outstanding."""
        kyc_guard = InMemoryKYCGuard()
        fatca_crs = InMemoryFatcaCrsGuard(default_complete=True)
        cid = "CUST-007"
        kyc_guard.set_status(cid, KYCStatus.APPROVED)
        engine = _make_engine(kyc_guard=kyc_guard, fatca_crs=fatca_crs)

        engine.transition(cid, LifecycleEvent.SUBMIT_APPLICATION)
        engine.transition(cid, LifecycleEvent.COMPLETE_KYC)
        engine.transition(cid, LifecycleEvent.ACTIVATE)

        # Mark reporting incomplete
        fatca_crs.mark_incomplete(cid)

        with pytest.raises(FatcaCrsIncompleteError, match="outstanding FATCA/CRS"):
            engine.transition(cid, LifecycleEvent.CLOSE)

        assert engine.get_state(cid) == CustomerState.ACTIVE

        # Mark reporting complete → close succeeds
        fatca_crs.mark_complete(cid)
        result = engine.transition(cid, LifecycleEvent.CLOSE)
        assert result is not None
        assert engine.get_state(cid) == CustomerState.CLOSED


# ── AC-6: blocked jurisdiction rejected (I-02) ───────────────────────────────


class TestBlockedJurisdictionCustomerRejected:
    def test_blocked_jurisdiction_customer_rejected(self) -> None:
        """I-02: SUBMIT_APPLICATION with blocked jurisdiction raises ValueError."""
        engine = _make_engine()
        cid = "CUST-008"

        for blocked in ("RU", "IR", "KP", "BY", "SY"):
            with pytest.raises(ValueError, match="blocked jurisdictions"):
                engine.transition(cid, LifecycleEvent.SUBMIT_APPLICATION, country=blocked)

        # Permitted jurisdiction succeeds
        result = engine.transition(cid, LifecycleEvent.SUBMIT_APPLICATION, country="GB")
        assert result is not None
        assert engine.get_state(cid) == CustomerState.ONBOARDING
