"""
tests/test_fee_management/test_fee_agent.py
IL-FME-01 | Phase 41 | 14 tests
"""

from __future__ import annotations

from decimal import Decimal

from services.fee_management.fee_agent import FeeAgent, HITLProposal
from services.fee_management.models import (
    FeeStatus,
    InMemoryFeeChargeStore,
    InMemoryFeeRuleStore,
    WaiverReason,
)


def _agent() -> tuple[FeeAgent, InMemoryFeeRuleStore, InMemoryFeeChargeStore]:
    rules = InMemoryFeeRuleStore()
    charges = InMemoryFeeChargeStore()
    return FeeAgent(rule_store=rules, charge_store=charges), rules, charges


class TestProcessCharge:
    def test_process_charge_returns_dict(self) -> None:
        agent, _, _ = _agent()
        result = agent.process_charge("acc-1", "rule-maintenance-001", "ref-001")
        assert "charge_id" in result

    def test_process_charge_autonomy_l1(self) -> None:
        agent, _, _ = _agent()
        result = agent.process_charge("acc-1", "rule-maintenance-001", "ref-001")
        assert result["autonomy_level"] == "L1"

    def test_process_charge_unknown_rule_returns_error(self) -> None:
        agent, _, _ = _agent()
        result = agent.process_charge("acc-1", "nonexistent-rule", "ref-001")
        assert "error" in result

    def test_process_charge_amount_as_string(self) -> None:
        agent, _, _ = _agent()
        result = agent.process_charge("acc-1", "rule-maintenance-001", "ref-002")
        assert isinstance(result["amount"], str)

    def test_process_charge_status_pending(self) -> None:
        agent, _, _ = _agent()
        result = agent.process_charge("acc-1", "rule-maintenance-001", "ref-003")
        assert result["status"] == FeeStatus.PENDING.value


class TestProcessWaiverRequest:
    def test_waiver_returns_hitl(self) -> None:
        agent, _, _ = _agent()
        proposal = agent.process_waiver_request(
            "charge-1", "acc-1", WaiverReason.GOODWILL, "user-1"
        )
        assert isinstance(proposal, HITLProposal)

    def test_waiver_autonomy_l4(self) -> None:
        agent, _, _ = _agent()
        proposal = agent.process_waiver_request(
            "charge-1", "acc-1", WaiverReason.PROMOTION, "user-1"
        )
        assert proposal.autonomy_level == "L4"

    def test_waiver_approver_compliance_officer(self) -> None:
        agent, _, _ = _agent()
        proposal = agent.process_waiver_request(
            "charge-1", "acc-1", WaiverReason.GOODWILL, "user-1"
        )
        assert (
            "COMPLIANCE" in proposal.requires_approval_from.upper()
            or "OFFICER" in proposal.requires_approval_from.upper()
        )


class TestProcessRefund:
    def test_refund_returns_hitl(self) -> None:
        agent, _, _ = _agent()
        proposal = agent.process_refund("charge-1", Decimal("5.00"), "overcharged")
        assert isinstance(proposal, HITLProposal)

    def test_refund_autonomy_l4(self) -> None:
        agent, _, _ = _agent()
        proposal = agent.process_refund("charge-1", Decimal("5.00"), "test")
        assert proposal.autonomy_level == "L4"


class TestProcessScheduleChange:
    def test_schedule_change_returns_hitl(self) -> None:
        agent, _, _ = _agent()
        proposal = agent.process_schedule_change("sched-1", {"rate": "0.02"})
        assert isinstance(proposal, HITLProposal)

    def test_schedule_change_approver_cfo(self) -> None:
        agent, _, _ = _agent()
        proposal = agent.process_schedule_change("sched-1", {})
        assert (
            "CFO" in proposal.requires_approval_from.upper()
            or "COMPLIANCE" in proposal.requires_approval_from.upper()
        )


class TestGetAgentStatus:
    def test_status_returns_dict(self) -> None:
        agent, _, _ = _agent()
        status = agent.get_agent_status()
        assert "agent" in status
        assert "status" in status
