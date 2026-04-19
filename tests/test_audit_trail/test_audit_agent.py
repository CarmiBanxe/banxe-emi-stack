"""
tests/test_audit_trail/test_audit_agent.py
IL-AES-01 | Phase 40 | banxe-emi-stack — 14 tests
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from services.audit_trail.audit_agent import AuditAgent, HITLProposal
from services.audit_trail.models import (
    AuditAction,
    EventCategory,
    SearchQuery,
    SourceSystem,
)


def _agent() -> AuditAgent:
    return AuditAgent()


class TestLogAuto:
    def test_log_returns_dict(self) -> None:
        agent = _agent()
        result = agent.process_log_request(
            EventCategory.PAYMENT,
            AuditAction.CREATE,
            "PAY-001",
            {"amount": "50.00"},
        )
        assert isinstance(result, dict)

    def test_log_returns_l1_autonomy(self) -> None:
        agent = _agent()
        result = agent.process_log_request(EventCategory.AUTH, AuditAction.READ, "SESS-1", {})
        assert result["autonomy_level"] == "L1"

    def test_log_returns_event_id(self) -> None:
        agent = _agent()
        result = agent.process_log_request(
            EventCategory.ADMIN, AuditAction.UPDATE, "CFG-1", {"field": "limit"}
        )
        assert "event_id" in result

    def test_log_chain_hash_present(self) -> None:
        agent = _agent()
        result = agent.process_log_request(EventCategory.AML, AuditAction.ESCALATE, "TX-1", {})
        assert "chain_hash" in result
        assert len(result["chain_hash"]) == 64


class TestSearchAuto:
    def test_search_returns_dict(self) -> None:
        agent = _agent()
        result = agent.process_search_request(SearchQuery())
        assert isinstance(result, dict)

    def test_search_returns_l1(self) -> None:
        agent = _agent()
        result = agent.process_search_request(SearchQuery())
        assert result["autonomy_level"] == "L1"

    def test_search_has_total(self) -> None:
        agent = _agent()
        result = agent.process_search_request(SearchQuery())
        assert "total" in result


class TestReplayAuto:
    def test_replay_returns_dict(self) -> None:
        agent = _agent()
        now = datetime.now(UTC)
        result = agent.process_replay_request("e-1", now - timedelta(hours=1), now)
        assert isinstance(result, dict)

    def test_replay_returns_l1(self) -> None:
        agent = _agent()
        now = datetime.now(UTC)
        result = agent.process_replay_request("e-1", now - timedelta(hours=1), now)
        assert result["autonomy_level"] == "L1"


class TestPurgeHITL:
    def test_purge_returns_hitl(self) -> None:
        agent = _agent()
        result = agent.process_purge_request(EventCategory.AML, 1825)
        assert isinstance(result, HITLProposal)

    def test_purge_is_l4(self) -> None:
        agent = _agent()
        result = agent.process_purge_request(EventCategory.PAYMENT, 2555)
        assert result.autonomy_level == "L4"

    def test_purge_requires_mlro(self) -> None:
        agent = _agent()
        result = agent.process_purge_request(EventCategory.AML, 365)
        assert result.requires_approval_from == "MLRO"


class TestIntegrityAuto:
    def test_integrity_returns_dict(self) -> None:
        agent = _agent()
        result = agent.process_integrity_check(SourceSystem.API)
        assert isinstance(result, dict)

    def test_integrity_returns_l1(self) -> None:
        agent = _agent()
        result = agent.process_integrity_check(SourceSystem.AGENT)
        assert result["autonomy_level"] == "L1"


class TestAgentStatus:
    def test_get_status(self) -> None:
        agent = _agent()
        status = agent.get_agent_status()
        assert status["agent"] == "AuditAgent"
        assert "hitl_gates" in status
