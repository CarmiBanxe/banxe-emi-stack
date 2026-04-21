"""
Tests for FX Agent.
IL-FXE-01 | Sprint 34 | Phase 48
Tests: L1 auto < £10k, L4 HITL ≥ £10k, reject/requote ALWAYS HITL (I-27)
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.fx_engine.fx_agent import LARGE_FX_THRESHOLD, FXAgent, HITLProposal
from services.fx_engine.fx_quoter import FXQuoter
from services.fx_engine.models import InMemoryQuoteStore, InMemoryRateStore


@pytest.fixture
def agent():
    quoter = FXQuoter(
        rate_store=InMemoryRateStore(),
        quote_store=InMemoryQuoteStore(),
    )
    return FXAgent(quoter=quoter)


@pytest.fixture
def agent_with_quote(agent):
    quote = agent._quoter.create_quote("GBP/EUR", Decimal("1000"), "GBP")
    return agent, quote


class TestProcessExecuteSmall:
    def test_execute_below_10k_auto(self, agent_with_quote):
        agent, quote = agent_with_quote
        result = agent.process_execute(quote.quote_id, Decimal("1000"))
        assert isinstance(result, dict)
        assert result["autonomy_level"] == "L1"

    def test_execute_below_10k_auto_approved(self, agent_with_quote):
        agent, quote = agent_with_quote
        result = agent.process_execute(quote.quote_id, Decimal("5000"))
        assert isinstance(result, dict)
        assert result["status"] == "AUTO_APPROVED"

    def test_execute_below_10k_returns_sell_amount(self, agent_with_quote):
        agent, quote = agent_with_quote
        result = agent.process_execute(quote.quote_id, Decimal("2000"))
        assert isinstance(result, dict)
        assert "sell_amount" in result

    def test_execute_expired_quote_returns_expired_dict(self, agent):
        result = agent.process_execute("nonexistent", Decimal("500"))
        assert isinstance(result, dict)
        assert result["autonomy_level"] == "L1"


class TestProcessExecuteLarge:
    def test_execute_at_10k_hitl(self, agent):
        result = agent.process_execute("qte_large", Decimal("10000"))
        assert isinstance(result, HITLProposal)

    def test_execute_above_10k_hitl(self, agent):
        result = agent.process_execute("qte_large", Decimal("50000"))
        assert isinstance(result, HITLProposal)
        assert result.autonomy_level == "L4"

    def test_execute_above_10k_requires_treasury_ops(self, agent):
        result = agent.process_execute("qte_large", Decimal("20000"))
        assert isinstance(result, HITLProposal)
        assert result.requires_approval_from == "TREASURY_OPS"

    def test_large_fx_threshold_constant(self):
        assert Decimal("10000") == LARGE_FX_THRESHOLD


class TestProcessReject:
    def test_reject_always_hitl(self, agent):
        result = agent.process_reject("qte_001", "Invalid counterparty")
        assert isinstance(result, HITLProposal)

    def test_reject_l4(self, agent):
        result = agent.process_reject("qte_001", "Reason")
        assert result.autonomy_level == "L4"

    def test_reject_requires_treasury_ops(self, agent):
        result = agent.process_reject("qte_001", "reason")
        assert result.requires_approval_from == "TREASURY_OPS"

    def test_reject_action_name(self, agent):
        result = agent.process_reject("qte_001", "reason")
        assert result.action == "REJECT_QUOTE"

    def test_reject_small_amount_still_hitl(self, agent):
        # Even tiny amounts require HITL for rejection
        result = agent.process_reject("qte_001", "test")
        assert isinstance(result, HITLProposal)


class TestProcessRequote:
    def test_requote_always_hitl(self, agent):
        result = agent.process_requote("GBP/EUR", Decimal("1000"))
        assert isinstance(result, HITLProposal)

    def test_requote_l4(self, agent):
        result = agent.process_requote("GBP/EUR", Decimal("1000"))
        assert result.autonomy_level == "L4"

    def test_requote_requires_treasury_ops(self, agent):
        result = agent.process_requote("GBP/EUR", Decimal("1000"))
        assert result.requires_approval_from == "TREASURY_OPS"

    def test_requote_action_name(self, agent):
        result = agent.process_requote("GBP/USD", Decimal("5000"))
        assert result.action == "REQUOTE"

    def test_requote_large_amount_still_hitl(self, agent):
        result = agent.process_requote("GBP/EUR", Decimal("100000"))
        assert isinstance(result, HITLProposal)


class TestGetAgentStatus:
    def test_status_structure(self, agent):
        status = agent.get_agent_status()
        assert "pending_executions" in status
        assert "pending_rejects" in status
        assert "large_fx_pending" in status
        assert "autonomy_level" in status

    def test_status_autonomy_level(self, agent):
        status = agent.get_agent_status()
        assert "L1" in status["autonomy_level"]
        assert "L4" in status["autonomy_level"]

    def test_large_fx_threshold_in_status(self, agent):
        status = agent.get_agent_status()
        assert status["l1_threshold_gbp"] == str(LARGE_FX_THRESHOLD)
