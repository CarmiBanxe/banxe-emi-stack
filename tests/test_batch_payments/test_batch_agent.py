"""
tests/test_batch_payments/test_batch_agent.py — Tests for BatchAgent
IL-BPP-01 | Phase 36 | 12 tests
I-27: Submission always HITL.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.batch_payments.batch_agent import BatchAgent, HITLProposal
from services.batch_payments.models import InMemoryAuditStore, InMemoryBatchStore


@pytest.fixture()
def agent():
    return BatchAgent(batch_port=InMemoryBatchStore(), audit_port=InMemoryAuditStore())


def test_process_submission_always_hitl(agent):
    result = agent.process_submission("batch-001", Decimal("1000"))
    assert isinstance(result, HITLProposal)


def test_process_submission_small_amount_still_hitl(agent):
    result = agent.process_submission("batch-002", Decimal("1"))
    assert isinstance(result, HITLProposal)


def test_process_submission_l4_autonomy(agent):
    result = agent.process_submission("batch-003", Decimal("500000"))
    assert result.autonomy_level == "L4"


def test_process_submission_resource_id_matches(agent):
    result = agent.process_submission("batch-match", Decimal("100"))
    assert result.resource_id == "batch-match"


def test_process_submission_requires_compliance_officer(agent):
    result = agent.process_submission("batch-004", Decimal("1000"))
    assert "Compliance" in result.requires_approval_from


def test_process_validation_returns_dict(agent):
    result = agent.process_validation("batch-005")
    assert isinstance(result, dict)
    assert result["status"] == "VALIDATED"


def test_process_validation_auto_l2(agent):
    result = agent.process_validation("batch-006")
    assert result["autonomy_level"] == "L2"


def test_process_reconciliation_returns_dict(agent):
    result = agent.process_reconciliation("batch-007")
    assert isinstance(result, dict)
    assert result["status"] == "RECONCILED"


def test_process_reconciliation_auto_l2(agent):
    result = agent.process_reconciliation("batch-008")
    assert result["autonomy_level"] == "L2"


def test_get_agent_status_returns_dict(agent):
    status = agent.get_agent_status()
    assert status["agent"] == "BatchAgent"
    assert status["status"] == "ACTIVE"


def test_get_agent_status_il_ref(agent):
    status = agent.get_agent_status()
    assert status["il_ref"] == "IL-BPP-01"


def test_get_agent_status_default_l4(agent):
    status = agent.get_agent_status()
    assert status["autonomy_level_default"] == "L4"
