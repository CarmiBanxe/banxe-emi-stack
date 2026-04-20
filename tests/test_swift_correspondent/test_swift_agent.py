"""
Tests for SWIFT Agent.
IL-SWF-01 | Sprint 34 | Phase 47
Tests: all send/hold/reject → HITLProposal (I-27), L1 validation auto
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.swift_correspondent.message_builder import SWIFTMessageBuilder
from services.swift_correspondent.models import InMemoryMessageStore
from services.swift_correspondent.swift_agent import HITLProposal, SWIFTAgent


@pytest.fixture
def agent():
    store = InMemoryMessageStore()
    builder = SWIFTMessageBuilder(store=store)
    return SWIFTAgent(builder=builder)


@pytest.fixture
def agent_with_message(agent):
    builder = agent._builder
    msg = builder.build_mt103(
        sender_bic="BARCGB22",
        receiver_bic="DEUTDEDB",
        amount=Decimal("1000"),
        currency="GBP",
        ordering_customer="A",
        beneficiary_customer="B",
        remittance_info="test",
    )
    return agent, msg.message_id


class TestProcessSend:
    def test_send_returns_hitl_proposal(self, agent):
        proposal = agent.process_send("msg_001")
        assert isinstance(proposal, HITLProposal)

    def test_send_always_l4(self, agent):
        proposal = agent.process_send("msg_001")
        assert proposal.autonomy_level == "L4"

    def test_send_requires_treasury_ops(self, agent):
        proposal = agent.process_send("msg_001")
        assert proposal.requires_approval_from == "TREASURY_OPS"

    def test_send_action_name(self, agent):
        proposal = agent.process_send("msg_001")
        assert proposal.action == "SEND_MESSAGE"

    def test_send_multiple_messages_all_hitl(self, agent):
        for i in range(3):
            proposal = agent.process_send(f"msg_{i:03d}")
            assert isinstance(proposal, HITLProposal)


class TestProcessHold:
    def test_hold_returns_hitl_proposal(self, agent):
        proposal = agent.process_hold("msg_001", "Compliance review")
        assert isinstance(proposal, HITLProposal)

    def test_hold_always_l4(self, agent):
        proposal = agent.process_hold("msg_001", "AML check")
        assert proposal.autonomy_level == "L4"

    def test_hold_reason_in_proposal(self, agent):
        proposal = agent.process_hold("msg_001", "My reason")
        assert "My reason" in proposal.reason

    def test_hold_requires_treasury_ops(self, agent):
        proposal = agent.process_hold("msg_001", "review")
        assert proposal.requires_approval_from == "TREASURY_OPS"


class TestProcessReject:
    def test_reject_returns_hitl_proposal(self, agent):
        proposal = agent.process_reject("msg_001", "Invalid")
        assert isinstance(proposal, HITLProposal)

    def test_reject_always_l4(self, agent):
        proposal = agent.process_reject("msg_001", "Blocked")
        assert proposal.autonomy_level == "L4"

    def test_reject_requires_treasury_ops(self, agent):
        proposal = agent.process_reject("msg_001", "reason")
        assert proposal.requires_approval_from == "TREASURY_OPS"

    def test_reject_action_name(self, agent):
        proposal = agent.process_reject("msg_001", "reason")
        assert proposal.action == "REJECT_MESSAGE"


class TestProcessValidation:
    def test_validation_returns_dict(self, agent_with_message):
        agent, message_id = agent_with_message
        result = agent.process_validation(message_id)
        assert isinstance(result, dict)

    def test_validation_l1_autonomy(self, agent_with_message):
        agent, message_id = agent_with_message
        result = agent.process_validation(message_id)
        assert result["autonomy_level"] == "L1"

    def test_validation_valid_message_true(self, agent_with_message):
        agent, message_id = agent_with_message
        result = agent.process_validation(message_id)
        assert result["is_valid"] is True

    def test_validation_invalid_message_false(self, agent):
        result = agent.process_validation("nonexistent")
        assert result["is_valid"] is False

    def test_validation_has_errors_list(self, agent_with_message):
        agent, message_id = agent_with_message
        result = agent.process_validation(message_id)
        assert "errors" in result
        assert isinstance(result["errors"], list)


class TestGetAgentStatus:
    def test_agent_status_structure(self, agent):
        status = agent.get_agent_status()
        assert "pending_sends" in status
        assert "pending_holds" in status
        assert "pending_rejects" in status
        assert "autonomy_level" in status

    def test_agent_status_l4_level(self, agent):
        status = agent.get_agent_status()
        assert status["autonomy_level"] == "L4"

    def test_pending_counts_increment(self, agent):
        agent.process_send("msg_001")
        agent.process_hold("msg_002", "reason")
        status = agent.get_agent_status()
        assert status["pending_sends"] == 1
        assert status["pending_holds"] == 1
