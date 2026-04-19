"""
tests/test_compliance_calendar/test_calendar_agent.py
IL-CCD-01 | Phase 42 | 12 tests
"""

from __future__ import annotations

from datetime import date, timedelta

from services.compliance_calendar.calendar_agent import CalendarAgent, HITLProposal
from services.compliance_calendar.models import (
    DeadlineType,
    InMemoryDeadlineStore,
    InMemoryReminderStore,
    Priority,
)


def _agent() -> CalendarAgent:
    return CalendarAgent(
        deadline_store=InMemoryDeadlineStore(),
        reminder_store=InMemoryReminderStore(),
    )


class TestProcessNewDeadline:
    def test_returns_dict(self) -> None:
        result = _agent().process_new_deadline(
            "Test DL",
            DeadlineType.CUSTOM,
            Priority.MEDIUM,
            date.today() + timedelta(days=60),
            "owner",
        )
        assert isinstance(result, dict)

    def test_autonomy_l1(self) -> None:
        result = _agent().process_new_deadline(
            "Test DL",
            DeadlineType.CUSTOM,
            Priority.MEDIUM,
            date.today() + timedelta(days=60),
            "owner",
        )
        assert result["autonomy_level"] == "L1"

    def test_reminders_scheduled(self) -> None:
        result = _agent().process_new_deadline(
            "Test DL",
            DeadlineType.FCA_RETURN,
            Priority.HIGH,
            date.today() + timedelta(days=90),
            "CFO",
        )
        assert result["reminders_scheduled"] > 0


class TestProcessDeadlineUpdate:
    def test_update_returns_hitl(self) -> None:
        agent = _agent()
        proposal = agent.process_deadline_update("dl-1", {"priority": "CRITICAL"})
        assert isinstance(proposal, HITLProposal)

    def test_update_autonomy_l4(self) -> None:
        agent = _agent()
        proposal = agent.process_deadline_update("dl-1", {})
        assert proposal.autonomy_level == "L4"


class TestProcessReminder:
    def test_returns_dict(self) -> None:
        result = _agent().process_reminder("dl-fca-fin060-q1")
        assert isinstance(result, dict)

    def test_autonomy_l1(self) -> None:
        result = _agent().process_reminder("dl-fca-fin060-q1")
        assert result["autonomy_level"] == "L1"


class TestProcessBoardReport:
    def test_returns_hitl(self) -> None:
        proposal = _agent().process_board_report(date(2026, 1, 1), date(2026, 3, 31))
        assert isinstance(proposal, HITLProposal)

    def test_autonomy_l4(self) -> None:
        proposal = _agent().process_board_report(date(2026, 1, 1), date(2026, 3, 31))
        assert proposal.autonomy_level == "L4"

    def test_approver_board(self) -> None:
        proposal = _agent().process_board_report(date(2026, 1, 1), date(2026, 3, 31))
        assert "BOARD" in proposal.requires_approval_from.upper()


class TestGetAgentStatus:
    def test_status_active(self) -> None:
        status = _agent().get_agent_status()
        assert status["status"] == "ACTIVE"

    def test_status_has_hitl_gates(self) -> None:
        status = _agent().get_agent_status()
        assert "hitl_gates" in status
