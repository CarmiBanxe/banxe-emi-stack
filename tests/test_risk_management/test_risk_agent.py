"""
tests/test_risk_management/test_risk_agent.py
IL-RMS-01 | Phase 37 | banxe-emi-stack — 14 tests
"""

from __future__ import annotations

from decimal import Decimal

from services.risk_management.models import (
    MitigationAction,
    RiskCategory,
    RiskThreshold,
)
from services.risk_management.risk_agent import HITLProposal, RiskAgent


def _agent() -> RiskAgent:
    return RiskAgent()


class TestProcessScoringRequest:
    def test_returns_dict(self) -> None:
        agent = _agent()
        result = agent.process_scoring_request("e-1", {"velocity": "50"}, RiskCategory.FRAUD)
        assert isinstance(result, dict)

    def test_has_entity_id(self) -> None:
        agent = _agent()
        result = agent.process_scoring_request("e-42", {}, RiskCategory.AML)
        assert result["entity_id"] == "e-42"

    def test_has_score_and_level(self) -> None:
        agent = _agent()
        result = agent.process_scoring_request("e-1", {"f": "30"}, RiskCategory.CREDIT)
        assert "score" in result
        assert "level" in result

    def test_score_is_string(self) -> None:
        agent = _agent()
        result = agent.process_scoring_request("e-1", {"f": "30"}, RiskCategory.FRAUD)
        assert isinstance(result["score"], str)

    def test_has_assessed_at(self) -> None:
        agent = _agent()
        result = agent.process_scoring_request("e-1", {}, RiskCategory.MARKET)
        assert "assessed_at" in result


class TestProcessThresholdChange:
    def test_always_returns_hitl(self) -> None:
        agent = _agent()
        threshold = RiskThreshold(
            RiskCategory.AML, Decimal("20"), Decimal("45"), Decimal("70"), True
        )
        result = agent.process_threshold_change(RiskCategory.AML, threshold)
        assert isinstance(result, HITLProposal)

    def test_autonomy_level_l4(self) -> None:
        agent = _agent()
        threshold = RiskThreshold(
            RiskCategory.FRAUD, Decimal("20"), Decimal("45"), Decimal("70"), True
        )
        result = agent.process_threshold_change(RiskCategory.FRAUD, threshold)
        assert result.autonomy_level == "L4"

    def test_requires_risk_officer(self) -> None:
        agent = _agent()
        threshold = RiskThreshold(
            RiskCategory.CREDIT, Decimal("20"), Decimal("45"), Decimal("70"), True
        )
        result = agent.process_threshold_change(RiskCategory.CREDIT, threshold)
        assert "Risk Officer" in result.requires_approval_from


class TestProcessMitigationUpdate:
    def test_accepted_returns_hitl(self) -> None:
        agent = _agent()
        result = agent.process_mitigation_update("plan-1", MitigationAction.ACCEPTED)
        assert isinstance(result, HITLProposal)

    def test_transferred_returns_hitl(self) -> None:
        agent = _agent()
        result = agent.process_mitigation_update("plan-1", MitigationAction.TRANSFERRED)
        assert isinstance(result, HITLProposal)

    def test_non_sensitive_action_creates_plan_first(self) -> None:
        agent = _agent()
        # Create a plan first, then update it
        from datetime import UTC, datetime, timedelta

        plan = agent._tracker.create_plan(
            "assess-1", "Fix", "Alice", datetime.now(UTC) + timedelta(days=10)
        )
        result = agent.process_mitigation_update(plan.id, MitigationAction.IN_PROGRESS)
        assert isinstance(result, dict)


class TestGetAgentStatus:
    def test_returns_dict(self) -> None:
        agent = _agent()
        result = agent.get_agent_status()
        assert isinstance(result, dict)

    def test_has_status_operational(self) -> None:
        agent = _agent()
        result = agent.get_agent_status()
        assert result["status"] == "operational"
