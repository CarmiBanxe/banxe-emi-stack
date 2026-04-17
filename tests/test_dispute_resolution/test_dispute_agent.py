"""
tests/test_dispute_resolution/test_dispute_agent.py — facade
IL-DRM-01 | Phase 33 | banxe-emi-stack
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.dispute_resolution.dispute_agent import DisputeAgent
from services.dispute_resolution.models import (
    DisputeStatus,
    DisputeType,
    EscalationLevel,
    EvidenceType,
    ResolutionOutcome,
)


def _agent() -> DisputeAgent:
    return DisputeAgent()


class TestOpenDispute:
    def test_returns_dispute_id(self) -> None:
        agent = _agent()
        result = agent.open_dispute(
            "c-1", "p-1", DisputeType.UNAUTHORIZED_TRANSACTION, Decimal("100.00")
        )
        assert "dispute_id" in result
        assert result["dispute_id"] != ""

    def test_status_opened(self) -> None:
        agent = _agent()
        result = agent.open_dispute("c-1", "p-1", DisputeType.DUPLICATE_CHARGE, Decimal("50.00"))
        assert result["status"] == DisputeStatus.OPENED.value

    def test_zero_amount_raises(self) -> None:
        agent = _agent()
        with pytest.raises(ValueError, match="positive"):
            agent.open_dispute("c-1", "p-1", DisputeType.DUPLICATE_CHARGE, Decimal("0"))

    def test_sla_deadline_present(self) -> None:
        agent = _agent()
        result = agent.open_dispute("c-1", "p-1", DisputeType.DUPLICATE_CHARGE, Decimal("50.00"))
        assert "sla_deadline" in result


class TestSubmitEvidence:
    def test_returns_evidence_id(self) -> None:
        agent = _agent()
        r = agent.open_dispute("c-1", "p-1", DisputeType.DUPLICATE_CHARGE, Decimal("50.00"))
        ev = agent.submit_evidence(r["dispute_id"], EvidenceType.RECEIPT, b"file_content")
        assert "evidence_id" in ev
        assert ev["evidence_id"] != ""

    def test_returns_sha256_hash(self) -> None:
        agent = _agent()
        r = agent.open_dispute("c-1", "p-1", DisputeType.DUPLICATE_CHARGE, Decimal("50.00"))
        ev = agent.submit_evidence(r["dispute_id"], EvidenceType.SCREENSHOT, b"data")
        assert len(ev["file_hash"]) == 64

    def test_unknown_dispute_raises(self) -> None:
        agent = _agent()
        with pytest.raises(ValueError, match="not found"):
            agent.submit_evidence("bad-id", EvidenceType.RECEIPT, b"data")


class TestGetDisputeStatus:
    def test_returns_correct_customer(self) -> None:
        agent = _agent()
        r = agent.open_dispute("c-99", "p-1", DisputeType.CREDIT_NOT_PROCESSED, Decimal("20.00"))
        detail = agent.get_dispute_status(r["dispute_id"])
        assert detail["customer_id"] == "c-99"

    def test_amount_as_string(self) -> None:
        agent = _agent()
        r = agent.open_dispute("c-1", "p-1", DisputeType.DUPLICATE_CHARGE, Decimal("42.00"))
        detail = agent.get_dispute_status(r["dispute_id"])
        assert detail["amount"] == "42.00"

    def test_unknown_raises(self) -> None:
        agent = _agent()
        with pytest.raises(ValueError, match="not found"):
            agent.get_dispute_status("nonexistent")


class TestProposeResolution:
    def test_always_hitl_required(self) -> None:
        agent = _agent()
        r = agent.open_dispute(
            "c-1", "p-1", DisputeType.UNAUTHORIZED_TRANSACTION, Decimal("100.00")
        )
        result = agent.propose_resolution(
            r["dispute_id"], ResolutionOutcome.UPHELD, Decimal("100.00")
        )
        assert result["status"] == "HITL_REQUIRED"

    def test_proposal_id_present(self) -> None:
        agent = _agent()
        r = agent.open_dispute(
            "c-1", "p-1", DisputeType.UNAUTHORIZED_TRANSACTION, Decimal("100.00")
        )
        result = agent.propose_resolution(r["dispute_id"], ResolutionOutcome.REJECTED)
        assert result["proposal_id"] != ""

    def test_outcome_in_result(self) -> None:
        agent = _agent()
        r = agent.open_dispute(
            "c-1", "p-1", DisputeType.UNAUTHORIZED_TRANSACTION, Decimal("100.00")
        )
        result = agent.propose_resolution(
            r["dispute_id"], ResolutionOutcome.PARTIAL_REFUND, Decimal("50.00")
        )
        assert result["outcome"] == ResolutionOutcome.PARTIAL_REFUND.value


class TestEscalate:
    def test_returns_escalation_id(self) -> None:
        agent = _agent()
        r = agent.open_dispute("c-1", "p-1", DisputeType.DUPLICATE_CHARGE, Decimal("50.00"))
        result = agent.escalate(r["dispute_id"], "SLA breach")
        assert result["escalation_id"] != ""

    def test_status_escalated(self) -> None:
        agent = _agent()
        r = agent.open_dispute("c-1", "p-1", DisputeType.DUPLICATE_CHARGE, Decimal("50.00"))
        result = agent.escalate(r["dispute_id"], "unresolved")
        assert result["status"] == DisputeStatus.ESCALATED.value

    def test_fos_level(self) -> None:
        agent = _agent()
        r = agent.open_dispute("c-1", "p-1", DisputeType.DUPLICATE_CHARGE, Decimal("50.00"))
        result = agent.escalate(r["dispute_id"], "FOS referral", EscalationLevel.FOS)
        assert result["level"] == EscalationLevel.FOS.value


class TestGetResolutionReport:
    def test_count_zero_for_unknown_customer(self) -> None:
        agent = _agent()
        result = agent.get_resolution_report("c-unknown")
        assert result["count"] == 0

    def test_count_matches_disputes_filed(self) -> None:
        agent = _agent()
        agent.open_dispute("c-1", "p-1", DisputeType.DUPLICATE_CHARGE, Decimal("50.00"))
        agent.open_dispute("c-1", "p-2", DisputeType.MERCHANDISE_NOT_RECEIVED, Decimal("75.00"))
        result = agent.get_resolution_report("c-1")
        assert result["count"] == 2
