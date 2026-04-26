"""Tests for Customer Lifecycle FSM (IL-LCY-01)."""

from __future__ import annotations

import pytest

from services.customer_lifecycle.lifecycle_engine import (
    _FSM,
    BLOCKED_JURISDICTIONS,
    InMemoryLifecycleStore,
    LifecycleEngine,
)
from services.customer_lifecycle.lifecycle_models import (
    CustomerState,
    DormancyConfig,
    LifecycleEvent,
    RetentionConfig,
)


def _make_engine() -> LifecycleEngine:
    return LifecycleEngine(InMemoryLifecycleStore())


class TestLifecycleFSMTransitions:
    def test_prospect_submit_application(self):
        engine = _make_engine()
        result = engine.transition("CUST001", LifecycleEvent.SUBMIT_APPLICATION)
        assert result is not None
        assert result.to_state == CustomerState.ONBOARDING

    def test_onboarding_complete_kyc(self):
        engine = _make_engine()
        engine.transition("CUST001", LifecycleEvent.SUBMIT_APPLICATION)
        result = engine.transition("CUST001", LifecycleEvent.COMPLETE_KYC)
        assert result is not None
        assert result.to_state == CustomerState.KYC_PENDING

    def test_kyc_pending_activate(self):
        engine = _make_engine()
        engine.transition("CUST001", LifecycleEvent.SUBMIT_APPLICATION)
        engine.transition("CUST001", LifecycleEvent.COMPLETE_KYC)
        result = engine.transition("CUST001", LifecycleEvent.ACTIVATE)
        assert result is not None
        assert result.to_state == CustomerState.ACTIVE

    def test_active_flag_dormant(self):
        engine = _make_engine()
        engine.transition("CUST001", LifecycleEvent.SUBMIT_APPLICATION)
        engine.transition("CUST001", LifecycleEvent.COMPLETE_KYC)
        engine.transition("CUST001", LifecycleEvent.ACTIVATE)
        result = engine.transition("CUST001", LifecycleEvent.FLAG_DORMANT)
        assert result is not None
        assert result.to_state == CustomerState.DORMANT

    def test_active_suspend(self):
        engine = _make_engine()
        engine.transition("CUST001", LifecycleEvent.SUBMIT_APPLICATION)
        engine.transition("CUST001", LifecycleEvent.COMPLETE_KYC)
        engine.transition("CUST001", LifecycleEvent.ACTIVATE)
        result = engine.transition("CUST001", LifecycleEvent.SUSPEND)
        assert result is not None
        assert result.to_state == CustomerState.SUSPENDED

    def test_active_close(self):
        engine = _make_engine()
        engine.transition("CUST001", LifecycleEvent.SUBMIT_APPLICATION)
        engine.transition("CUST001", LifecycleEvent.COMPLETE_KYC)
        engine.transition("CUST001", LifecycleEvent.ACTIVATE)
        result = engine.transition("CUST001", LifecycleEvent.CLOSE)
        assert result is not None
        assert result.to_state == CustomerState.CLOSED

    def test_closed_offboard(self):
        engine = _make_engine()
        engine.transition("CUST001", LifecycleEvent.SUBMIT_APPLICATION)
        engine.transition("CUST001", LifecycleEvent.COMPLETE_KYC)
        engine.transition("CUST001", LifecycleEvent.ACTIVATE)
        engine.transition("CUST001", LifecycleEvent.CLOSE)
        result = engine.transition("CUST001", LifecycleEvent.OFFBOARD)
        assert result is not None
        assert result.to_state == CustomerState.OFFBOARDED

    def test_invalid_transition_returns_none(self):
        """Cannot jump from PROSPECT directly to ACTIVE."""
        engine = _make_engine()
        result = engine.transition("CUST001", LifecycleEvent.ACTIVATE)
        assert result is None

    def test_offboarded_has_no_transitions(self):
        assert _FSM.get(CustomerState.OFFBOARDED) == {}

    def test_default_state_is_prospect(self):
        engine = _make_engine()
        state = engine.get_state("NEW_CUSTOMER")
        assert state == CustomerState.PROSPECT

    def test_blocked_jurisdiction_ru_raises(self):
        """I-02: RU country rejected on onboarding."""
        engine = _make_engine()
        with pytest.raises(ValueError, match="I-02"):
            engine.transition("CUST001", LifecycleEvent.SUBMIT_APPLICATION, country="RU")

    def test_blocked_jurisdiction_ir_raises(self):
        engine = _make_engine()
        with pytest.raises(ValueError):
            engine.transition("CUST001", LifecycleEvent.SUBMIT_APPLICATION, country="IR")

    def test_allowed_jurisdiction_gb_passes(self):
        engine = _make_engine()
        result = engine.transition("CUST001", LifecycleEvent.SUBMIT_APPLICATION, country="GB")
        assert result is not None
        assert result.to_state == CustomerState.ONBOARDING

    def test_transition_log_append_only(self):
        """I-24: transition_log grows."""
        engine = _make_engine()
        engine.transition("CUST001", LifecycleEvent.SUBMIT_APPLICATION)
        engine.transition("CUST001", LifecycleEvent.COMPLETE_KYC)
        assert len(engine.transition_log) == 2

    def test_transition_result_has_from_to_states(self):
        engine = _make_engine()
        result = engine.transition("CUST001", LifecycleEvent.SUBMIT_APPLICATION)
        assert result is not None
        assert result.from_state == CustomerState.PROSPECT
        assert result.to_state == CustomerState.ONBOARDING

    def test_get_history_returns_transitions(self):
        engine = _make_engine()
        engine.transition("CUST001", LifecycleEvent.SUBMIT_APPLICATION)
        engine.transition("CUST001", LifecycleEvent.COMPLETE_KYC)
        history = engine.get_history("CUST001")
        assert len(history) == 2

    def test_list_dormant_returns_dormant_customers(self):
        engine = _make_engine()
        for cid in ["C1", "C2"]:
            engine.transition(cid, LifecycleEvent.SUBMIT_APPLICATION)
            engine.transition(cid, LifecycleEvent.COMPLETE_KYC)
            engine.transition(cid, LifecycleEvent.ACTIVATE)
            engine.transition(cid, LifecycleEvent.FLAG_DORMANT)
        dormant = engine.list_dormant()
        assert len(dormant) == 2

    def test_dormancy_config_default(self):
        config = DormancyConfig()
        assert config.inactivity_days == 90

    def test_retention_config_default(self):
        """FCA SYSC 9: 5-year data retention."""
        config = RetentionConfig()
        assert config.years == 5

    def test_blocked_jurisdictions_set(self):
        assert "RU" in BLOCKED_JURISDICTIONS
        assert "GB" not in BLOCKED_JURISDICTIONS

    def test_state_enum_values(self):
        assert CustomerState.PROSPECT == "prospect"
        assert CustomerState.ACTIVE == "active"
        assert CustomerState.OFFBOARDED == "offboarded"

    def test_event_enum_values(self):
        assert LifecycleEvent.SUBMIT_APPLICATION == "submit_application"
        assert LifecycleEvent.OFFBOARD == "offboard"


class TestLifecycleAgent:
    def test_propose_suspend_returns_proposal(self):
        from services.customer_lifecycle.lifecycle_agent import (
            LifecycleAgent,
            LifecycleHITLProposal,
        )

        agent = LifecycleAgent()
        proposal = agent.propose_suspend("CUST001", "AML flag")
        assert isinstance(proposal, LifecycleHITLProposal)

    def test_suspend_requires_compliance_officer(self):
        """I-27: suspend requires COMPLIANCE_OFFICER."""
        from services.customer_lifecycle.lifecycle_agent import LifecycleAgent

        agent = LifecycleAgent()
        proposal = agent.propose_suspend("CUST001", "AML flag")
        assert proposal.requires_approval_from == "COMPLIANCE_OFFICER"

    def test_offboard_requires_head_of_compliance(self):
        """I-27: offboard requires HEAD_OF_COMPLIANCE (data deletion)."""
        from services.customer_lifecycle.lifecycle_agent import LifecycleAgent

        agent = LifecycleAgent()
        proposal = agent.propose_offboard("CUST001", "5-year retention complete")
        assert proposal.requires_approval_from == "HEAD_OF_COMPLIANCE"

    def test_suspend_not_auto_approved(self):
        """I-27: proposals start unapproved."""
        from services.customer_lifecycle.lifecycle_agent import LifecycleAgent

        agent = LifecycleAgent()
        proposal = agent.propose_suspend("CUST001", "reason")
        assert proposal.approved is False

    def test_offboard_not_auto_approved(self):
        from services.customer_lifecycle.lifecycle_agent import LifecycleAgent

        agent = LifecycleAgent()
        proposal = agent.propose_offboard("CUST001", "reason")
        assert proposal.approved is False

    def test_reactivate_requires_compliance_officer(self):
        from services.customer_lifecycle.lifecycle_agent import LifecycleAgent

        agent = LifecycleAgent()
        proposal = agent.propose_reactivate("CUST001", "customer requested")
        assert proposal.requires_approval_from == "COMPLIANCE_OFFICER"

    def test_proposals_accumulate(self):
        from services.customer_lifecycle.lifecycle_agent import LifecycleAgent

        agent = LifecycleAgent()
        agent.propose_suspend("C1", "AML")
        agent.propose_offboard("C2", "retention")
        assert len(agent.proposals) == 2
