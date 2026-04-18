"""
tests/test_crypto_custody/test_crypto_agent.py — Tests for CryptoAgent
IL-CDC-01 | Phase 35 | 16 tests
I-27: HITL at £1k. L2 below. Archive always L4.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.crypto_custody.crypto_agent import CryptoAgent, HITLProposal


@pytest.fixture()
def agent():
    return CryptoAgent()


def test_small_transfer_returns_dict_not_hitl(agent):
    result = agent.process_transfer_request("txfr-001", Decimal("999.99"))
    assert not isinstance(result, HITLProposal)
    assert isinstance(result, dict)


def test_large_transfer_returns_hitl(agent):
    result = agent.process_transfer_request("txfr-002", Decimal("1000"))
    assert isinstance(result, HITLProposal)


def test_transfer_above_threshold_hitl_l4(agent):
    result = agent.process_transfer_request("txfr-003", Decimal("5000"))
    assert isinstance(result, HITLProposal)
    assert result.autonomy_level == "L4"


def test_small_transfer_autonomy_level_l2(agent):
    result = agent.process_transfer_request("txfr-004", Decimal("100"))
    assert result["autonomy_level"] == "L2"


def test_transfer_at_exact_threshold_is_hitl(agent):
    result = agent.process_transfer_request("txfr-005", Decimal("1000"))
    assert isinstance(result, HITLProposal)


def test_archive_always_returns_hitl(agent):
    result = agent.process_archive_request("wallet-001")
    assert isinstance(result, HITLProposal)


def test_archive_always_l4(agent):
    result = agent.process_archive_request("wallet-002")
    assert result.autonomy_level == "L4"


def test_archive_requires_compliance_officer(agent):
    result = agent.process_archive_request("wallet-003")
    assert "Compliance" in result.requires_approval_from


def test_travel_rule_blocked_jurisdiction(agent):
    result = agent.process_travel_rule("txfr-006", Decimal("100"), "RU")
    assert result["decision"] == "BLOCKED"


def test_travel_rule_edd_required_greylist(agent):
    result = agent.process_travel_rule("txfr-007", Decimal("100"), "NG")
    assert result["decision"] == "EDD_REQUIRED"


def test_travel_rule_pass_clean_jurisdiction(agent):
    result = agent.process_travel_rule("txfr-008", Decimal("100"), "GB")
    assert result["decision"] == "PASS"


def test_travel_rule_sets_travel_rule_required_flag(agent):
    result = agent.process_travel_rule("txfr-009", Decimal("1000"), "GB")
    assert result["travel_rule_required"] == "True"


def test_travel_rule_not_required_below_threshold(agent):
    result = agent.process_travel_rule("txfr-010", Decimal("500"), "GB")
    assert result["travel_rule_required"] == "False"


def test_get_agent_status_returns_dict(agent):
    status = agent.get_agent_status()
    assert status["agent"] == "CryptoAgent"
    assert status["status"] == "ACTIVE"


def test_get_agent_status_il_ref(agent):
    status = agent.get_agent_status()
    assert status["il_ref"] == "IL-CDC-01"


def test_hitl_proposal_resource_id_matches(agent):
    result = agent.process_transfer_request("txfr-match", Decimal("2000"))
    assert isinstance(result, HITLProposal)
    assert result.resource_id == "txfr-match"
