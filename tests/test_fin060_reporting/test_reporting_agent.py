"""
tests/test_fin060_reporting/test_reporting_agent.py — ReportingAgent tests
IL-FIN060-01 | Phase 51C | Sprint 36
≥15 tests covering run_monthly_fin060, approve_and_submit, get_report, get_dashboard
"""

from __future__ import annotations

import pytest

from services.reporting.fin060_generator_v2 import HITLProposal
from services.reporting.report_models import FIN060Report, InMemoryReportStore
from services.reporting.reporting_agent import ReportingAgent


@pytest.fixture
def agent() -> ReportingAgent:
    return ReportingAgent(store=InMemoryReportStore())


def test_run_monthly_fin060_returns_hitl(agent: ReportingAgent) -> None:
    result = agent.run_monthly_fin060(4, 2026)
    assert isinstance(result, HITLProposal)


def test_run_monthly_fin060_requires_cfo(agent: ReportingAgent) -> None:
    result = agent.run_monthly_fin060(4, 2026)
    assert result.requires_approval_from == "CFO"


def test_run_monthly_fin060_autonomy_l4(agent: ReportingAgent) -> None:
    result = agent.run_monthly_fin060(4, 2026)
    assert result.autonomy_level == "L4"


def test_run_monthly_fin060_action_field(agent: ReportingAgent) -> None:
    result = agent.run_monthly_fin060(4, 2026)
    assert result.action == "generate_fin060"


def test_run_monthly_fin060_with_ledger_data(agent: ReportingAgent) -> None:
    ledger = [{"account_type": "safeguarding", "balance": "100000.00", "currency": "GBP"}]
    result = agent.run_monthly_fin060(4, 2026, ledger)
    assert isinstance(result, HITLProposal)


def test_approve_and_submit_returns_hitl(agent: ReportingAgent) -> None:
    result = agent.approve_and_submit("rpt001", "cfo_user")
    assert isinstance(result, HITLProposal)


def test_approve_and_submit_requires_cfo(agent: ReportingAgent) -> None:
    result = agent.approve_and_submit("rpt001", "cfo_user")
    assert result.requires_approval_from == "CFO"


def test_approve_and_submit_action_field(agent: ReportingAgent) -> None:
    result = agent.approve_and_submit("rpt001", "cfo_user")
    assert result.action == "approve_fin060"


def test_get_report_none_if_not_generated(agent: ReportingAgent) -> None:
    result = agent.get_report(1, 2020)
    assert result is None


def test_get_report_returns_report_after_generate(agent: ReportingAgent) -> None:
    agent.run_monthly_fin060(4, 2026)
    report = agent.get_report(4, 2026)
    assert report is not None
    assert isinstance(report, FIN060Report)


def test_get_dashboard_returns_dict(agent: ReportingAgent) -> None:
    result = agent.get_dashboard()
    assert isinstance(result, dict)


def test_get_dashboard_total_reports(agent: ReportingAgent) -> None:
    agent.run_monthly_fin060(1, 2026)
    agent.run_monthly_fin060(2, 2026)
    result = agent.get_dashboard()
    assert result["total_reports"] == 2


def test_get_dashboard_pending_approval(agent: ReportingAgent) -> None:
    agent.run_monthly_fin060(4, 2026)
    result = agent.get_dashboard()
    assert result["pending_approval"] == 1


def test_get_dashboard_safeguarded_gbp_str(agent: ReportingAgent) -> None:
    agent.run_monthly_fin060(4, 2026)
    result = agent.get_dashboard()
    assert isinstance(result["safeguarded_gbp"], str)


def test_invalid_month_raises(agent: ReportingAgent) -> None:
    with pytest.raises(ValueError, match="Invalid month"):
        agent.run_monthly_fin060(13, 2026)


def test_invalid_year_raises(agent: ReportingAgent) -> None:
    with pytest.raises(ValueError, match="Invalid year"):
        agent.run_monthly_fin060(4, 2019)
