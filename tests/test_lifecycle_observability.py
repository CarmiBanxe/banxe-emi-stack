"""Tests for Lifecycle Observability Port (IL-OBS-01)."""

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
from services.customer_lifecycle.lifecycle_models import CustomerState, LifecycleEvent
from services.customer_lifecycle.lifecycle_observer import (
    EddBreachObservedEvent,
    GuardFailureEvent,
    InMemoryLifecycleObserver,
    TransitionObservedEvent,
    _decimal_str,
)
from services.kyc.kyc_port import KYCStatus

# ── helpers ──────────────────────────────────────────────────────────────────


def _make_engine(
    observer: InMemoryLifecycleObserver | None = None,
    kyc_approved: bool = False,
    fatca_complete: bool = True,
) -> tuple[
    KYCLifecycleEngine, InMemoryLifecycleObserver, InMemoryKYCGuard, InMemoryHITLLifecyclePort
]:
    obs = observer or InMemoryLifecycleObserver()
    kyc = InMemoryKYCGuard(default=KYCStatus.APPROVED if kyc_approved else KYCStatus.PENDING)
    fatca = InMemoryFatcaCrsGuard(default_complete=fatca_complete)
    hitl = InMemoryHITLLifecyclePort()
    eng = KYCLifecycleEngine(kyc_guard=kyc, fatca_crs=fatca, hitl=hitl, observer=obs)
    return eng, obs, kyc, hitl


def _reach_active(eng: KYCLifecycleEngine, cid: str, kyc: InMemoryKYCGuard) -> None:
    """Bring a customer from PROSPECT to ACTIVE."""
    kyc.set_status(cid, KYCStatus.APPROVED)
    eng.transition(cid, LifecycleEvent.SUBMIT_APPLICATION)
    eng.transition(cid, LifecycleEvent.COMPLETE_KYC)
    eng.transition(cid, LifecycleEvent.ACTIVATE)


# ── InMemoryLifecycleObserver unit tests ─────────────────────────────────────


class TestInMemoryLifecycleObserver:
    def test_initial_state_empty(self) -> None:
        obs = InMemoryLifecycleObserver()
        assert obs.transitions == []
        assert obs.guard_failures == []
        assert obs.edd_breaches == []

    def test_on_transition_appends(self) -> None:
        obs = InMemoryLifecycleObserver()
        evt = TransitionObservedEvent(
            customer_id="C-001",
            from_state=CustomerState.KYC_PENDING,
            to_state=CustomerState.ACTIVE,
            lifecycle_event=LifecycleEvent.ACTIVATE,
        )
        obs.on_transition(evt)
        assert len(obs.transitions) == 1
        assert obs.transitions[0].customer_id == "C-001"

    def test_on_guard_failure_appends(self) -> None:
        obs = InMemoryLifecycleObserver()
        evt = GuardFailureEvent(
            customer_id="C-002",
            guard_type="KYC_NOT_APPROVED",
            detail="pending",
        )
        obs.on_guard_failure(evt)
        assert len(obs.guard_failures) == 1
        assert obs.guard_failures[0].guard_type == "KYC_NOT_APPROVED"

    def test_on_edd_breach_appends(self) -> None:
        obs = InMemoryLifecycleObserver()
        evt = EddBreachObservedEvent(
            customer_id="C-003",
            amount="15000",
            threshold="10000",
            entity_type="INDIVIDUAL",
        )
        obs.on_edd_breach(evt)
        assert len(obs.edd_breaches) == 1
        assert obs.edd_breaches[0].amount == "15000"

    def test_total_events_sums_all_logs(self) -> None:
        obs = InMemoryLifecycleObserver()
        obs.on_transition(
            TransitionObservedEvent(
                "C-1",
                CustomerState.PROSPECT,
                CustomerState.ONBOARDING,
                LifecycleEvent.SUBMIT_APPLICATION,
            )
        )
        obs.on_guard_failure(GuardFailureEvent("C-1", "KYC_NOT_APPROVED", "x"))
        obs.on_edd_breach(EddBreachObservedEvent("C-1", "12000", "10000", "INDIVIDUAL"))
        assert obs.total_events() == 3

    def test_transitions_returns_copy(self) -> None:
        """I-24: returned list is a copy — mutating it does not affect internal log."""
        obs = InMemoryLifecycleObserver()
        obs.on_transition(
            TransitionObservedEvent(
                "C-1",
                CustomerState.PROSPECT,
                CustomerState.ONBOARDING,
                LifecycleEvent.SUBMIT_APPLICATION,
            )
        )
        copy = obs.transitions
        copy.clear()
        assert len(obs.transitions) == 1  # internal log unchanged

    def test_multiple_guard_failures_append_in_order(self) -> None:
        obs = InMemoryLifecycleObserver()
        for i in range(5):
            obs.on_guard_failure(GuardFailureEvent(f"C-{i}", "KYC_NOT_APPROVED", "x"))
        assert [e.customer_id for e in obs.guard_failures] == [f"C-{i}" for i in range(5)]


# ── KYCLifecycleEngine — successful transition observability ──────────────────


class TestTransitionObserved:
    def test_submit_application_emits_transition(self) -> None:
        eng, obs, _kyc, _hitl = _make_engine()
        eng.transition("C-001", LifecycleEvent.SUBMIT_APPLICATION)
        assert len(obs.transitions) == 1
        assert obs.transitions[0].from_state == CustomerState.PROSPECT
        assert obs.transitions[0].to_state == CustomerState.ONBOARDING
        assert obs.transitions[0].lifecycle_event == LifecycleEvent.SUBMIT_APPLICATION

    def test_full_onboarding_to_active_emits_three_transitions(self) -> None:
        eng, obs, kyc, _hitl = _make_engine()
        _reach_active(eng, "C-001", kyc)
        # SUBMIT_APPLICATION + COMPLETE_KYC + ACTIVATE
        assert len(obs.transitions) == 3

    def test_transition_event_customer_id_matches(self) -> None:
        eng, obs, _kyc, _hitl = _make_engine()
        eng.transition("C-007", LifecycleEvent.SUBMIT_APPLICATION)
        assert obs.transitions[0].customer_id == "C-007"

    def test_transition_event_occurred_at_is_set(self) -> None:
        eng, obs, _kyc, _hitl = _make_engine()
        eng.transition("C-008", LifecycleEvent.SUBMIT_APPLICATION)
        assert obs.transitions[0].occurred_at  # non-empty ISO timestamp

    def test_no_observer_does_not_raise(self) -> None:
        """Backward-compat: no observer injected → transitions still work."""
        eng = KYCLifecycleEngine()
        eng.transition("C-000", LifecycleEvent.SUBMIT_APPLICATION)
        assert eng.get_state("C-000") == CustomerState.ONBOARDING

    def test_invalid_transition_emits_no_event(self) -> None:
        """Transitions that return None (invalid) do not emit a TransitionObservedEvent."""
        eng, obs, _kyc, _hitl = _make_engine()
        # SUSPEND from PROSPECT is invalid
        result = eng.transition("C-009", LifecycleEvent.SUSPEND)
        assert result is None
        assert len(obs.transitions) == 0


# ── Guard failure observability ───────────────────────────────────────────────


class TestGuardFailureObserved:
    def test_kyc_not_approved_emits_guard_failure(self) -> None:
        eng, obs, _kyc, _hitl = _make_engine(kyc_approved=False)
        eng.transition("C-001", LifecycleEvent.SUBMIT_APPLICATION)
        eng.transition("C-001", LifecycleEvent.COMPLETE_KYC)
        with pytest.raises(KYCNotApprovedError):
            eng.transition("C-001", LifecycleEvent.ACTIVATE)
        assert len(obs.guard_failures) == 1
        assert obs.guard_failures[0].guard_type == "KYC_NOT_APPROVED"
        assert obs.guard_failures[0].customer_id == "C-001"

    def test_hitl_required_emits_guard_failure(self) -> None:
        eng, obs, kyc, _hitl = _make_engine()
        _reach_active(eng, "C-002", kyc)
        eng.transition("C-002", LifecycleEvent.SUSPEND)
        with pytest.raises(HITLRequiredError):
            eng.transition("C-002", LifecycleEvent.ACTIVATE)
        hitl_failures = [e for e in obs.guard_failures if e.guard_type == "HITL_REQUIRED"]
        assert len(hitl_failures) == 1
        assert hitl_failures[0].customer_id == "C-002"

    def test_fatca_crs_incomplete_emits_guard_failure(self) -> None:
        eng, obs, kyc, _hitl = _make_engine(fatca_complete=False)
        _reach_active(eng, "C-003", kyc)
        with pytest.raises(FatcaCrsIncompleteError):
            eng.transition("C-003", LifecycleEvent.CLOSE)
        fatca_failures = [e for e in obs.guard_failures if e.guard_type == "FATCA_CRS_INCOMPLETE"]
        assert len(fatca_failures) == 1

    def test_guard_failure_detail_contains_customer_id(self) -> None:
        eng, obs, _kyc, _hitl = _make_engine(kyc_approved=False)
        eng.transition("C-004", LifecycleEvent.SUBMIT_APPLICATION)
        eng.transition("C-004", LifecycleEvent.COMPLETE_KYC)
        with pytest.raises(KYCNotApprovedError):
            eng.transition("C-004", LifecycleEvent.ACTIVATE)
        assert "C-004" in obs.guard_failures[0].detail

    def test_guard_failure_and_success_both_logged(self) -> None:
        """Two customers: one fails KYC guard, other submits successfully."""
        eng, obs, _kyc, _hitl = _make_engine(kyc_approved=False)
        # C-010: reaches KYC_PENDING, then fails ACTIVATE guard
        eng.transition("C-010", LifecycleEvent.SUBMIT_APPLICATION)
        eng.transition("C-010", LifecycleEvent.COMPLETE_KYC)
        with pytest.raises(KYCNotApprovedError):
            eng.transition("C-010", LifecycleEvent.ACTIVATE)
        # C-011: only SUBMIT_APPLICATION
        eng.transition("C-011", LifecycleEvent.SUBMIT_APPLICATION)
        assert len(obs.guard_failures) == 1
        assert obs.guard_failures[0].customer_id == "C-010"
        submit_events = [
            t for t in obs.transitions if t.lifecycle_event == LifecycleEvent.SUBMIT_APPLICATION
        ]
        assert len(submit_events) == 2


# ── EDD breach observability ──────────────────────────────────────────────────


class TestEddBreachObserved:
    def test_edd_breach_emits_event(self) -> None:
        eng, obs, kyc, _hitl = _make_engine()
        _reach_active(eng, "C-005", kyc)
        with pytest.raises(EddBreachError):
            eng.trigger_edd_restriction("C-005", Decimal("15000"), "INDIVIDUAL")
        assert len(obs.edd_breaches) == 1
        breach = obs.edd_breaches[0]
        assert breach.customer_id == "C-005"
        assert breach.entity_type == "INDIVIDUAL"

    def test_edd_breach_amounts_are_strings_not_float(self) -> None:
        """I-01: amounts stored as Decimal strings, never float."""
        eng, obs, kyc, _hitl = _make_engine()
        _reach_active(eng, "C-006", kyc)
        with pytest.raises(EddBreachError):
            eng.trigger_edd_restriction("C-006", Decimal("12500.50"), "INDIVIDUAL")
        breach = obs.edd_breaches[0]
        assert isinstance(breach.amount, str)
        assert isinstance(breach.threshold, str)
        assert Decimal(breach.amount) == Decimal("12500.50")

    def test_below_edd_threshold_emits_no_event(self) -> None:
        eng, obs, kyc, _hitl = _make_engine()
        _reach_active(eng, "C-007", kyc)
        result = eng.trigger_edd_restriction("C-007", Decimal("500"), "INDIVIDUAL")
        assert result is None
        assert len(obs.edd_breaches) == 0

    def test_edd_corporate_threshold_below_does_not_breach(self) -> None:
        """Corporate EDD trigger is £50k (I-04)."""
        eng, obs, kyc, _hitl = _make_engine()
        _reach_active(eng, "C-008", kyc)
        result = eng.trigger_edd_restriction("C-008", Decimal("49999.99"), "COMPANY")
        assert result is None
        assert len(obs.edd_breaches) == 0

    def test_decimal_str_helper_returns_plain_string(self) -> None:
        """_decimal_str serialises Decimal to plain string (I-01, I-05)."""
        assert _decimal_str(Decimal("10000")) == "10000"
        assert _decimal_str(Decimal("12345.67")) == "12345.67"

    def test_edd_breach_observer_called_before_error_raised(self) -> None:
        """Observer records the breach even though EddBreachError is raised."""
        eng, obs, kyc, _hitl = _make_engine()
        _reach_active(eng, "C-009", kyc)
        captured: list[EddBreachObservedEvent] = []

        class CapturingObserver(InMemoryLifecycleObserver):
            def on_edd_breach(self, event: EddBreachObservedEvent) -> None:
                captured.append(event)
                super().on_edd_breach(event)

        cap_obs = CapturingObserver()
        eng2, _, kyc2, _ = _make_engine(observer=cap_obs)
        _reach_active(eng2, "C-999", kyc2)
        with pytest.raises(EddBreachError):
            eng2.trigger_edd_restriction("C-999", Decimal("11000"), "INDIVIDUAL")
        assert len(captured) == 1
