"""
tests/test_reporting_analytics/test_analytics_agent.py
IL-RAP-01 | Phase 38 | banxe-emi-stack — 12 tests
"""

from __future__ import annotations

import pytest

from services.reporting_analytics.analytics_agent import AnalyticsAgent, HITLProposal
from services.reporting_analytics.models import ReportFormat


def _agent_with_template() -> tuple[AnalyticsAgent, str]:
    agent = AnalyticsAgent()
    templates = agent._builder._templates.list_templates()
    tid = templates[0].id
    return agent, tid


class TestProcessReportRequest:
    def test_returns_dict(self) -> None:
        agent, tid = _agent_with_template()
        result = agent.process_report_request(tid, {})
        assert isinstance(result, dict)

    def test_has_job_id(self) -> None:
        agent, tid = _agent_with_template()
        result = agent.process_report_request(tid, {})
        assert "job_id" in result

    def test_status_completed(self) -> None:
        agent, tid = _agent_with_template()
        result = agent.process_report_request(tid, {})
        assert result["status"] == "COMPLETED"

    def test_invalid_template_raises(self) -> None:
        agent, _ = _agent_with_template()
        with pytest.raises(ValueError, match="not found"):
            agent.process_report_request("bad-template", {})


class TestProcessScheduleChange:
    def test_always_returns_hitl(self) -> None:
        agent, _ = _agent_with_template()
        result = agent.process_schedule_change("sched-1", {"frequency": "WEEKLY"})
        assert isinstance(result, HITLProposal)

    def test_autonomy_level_l4(self) -> None:
        agent, _ = _agent_with_template()
        result = agent.process_schedule_change("sched-1", {})
        assert result.autonomy_level == "L4"

    def test_requires_analytics_manager(self) -> None:
        agent, _ = _agent_with_template()
        result = agent.process_schedule_change("sched-1", {})
        assert "Analytics Manager" in result.requires_approval_from


class TestProcessExportRequest:
    def test_returns_dict(self) -> None:
        agent, tid = _agent_with_template()
        job_result = agent.process_report_request(tid, {})
        result = agent.process_export_request(job_result["job_id"], ReportFormat.JSON, True)
        assert isinstance(result, dict)

    def test_has_file_hash(self) -> None:
        agent, tid = _agent_with_template()
        job_result = agent.process_report_request(tid, {})
        result = agent.process_export_request(job_result["job_id"], ReportFormat.CSV, True)
        assert "file_hash" in result


class TestGetAgentStatus:
    def test_returns_dict(self) -> None:
        agent, _ = _agent_with_template()
        result = agent.get_agent_status()
        assert isinstance(result, dict)

    def test_is_operational(self) -> None:
        agent, _ = _agent_with_template()
        result = agent.get_agent_status()
        assert result["status"] == "operational"
