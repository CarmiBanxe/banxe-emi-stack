"""
tests/test_consumer_duty/test_consumer_duty_reporter.py
Tests for ConsumerDutyReporter: annual report, dashboard, board report HITL.
IL-CDO-01 | Phase 50 | Sprint 35 | BT-005 resolved

≥15 tests covering:
- generate_annual_report returns structured PS22/9 s.1.4 assessment (BT-005)
- generate_outcome_dashboard structure
- export_board_report returns HITLProposal (I-27, CFO approval)
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from services.consumer_duty.consumer_duty_reporter import ConsumerDutyReporter
from services.consumer_duty.models_v2 import (
    HITLProposal,
    InMemoryOutcomeStore,
    InMemoryProductGovernance,
    InMemoryVulnerabilityAlertStore,
    InterventionType,
    OutcomeType,
    ProductGovernanceRecord,
    VulnerabilityAlert,
    VulnerabilityFlag,
)
from services.consumer_duty.outcome_assessor import OutcomeAssessor


def ts() -> str:
    return datetime.now(UTC).isoformat()


def make_reporter() -> tuple[
    ConsumerDutyReporter,
    InMemoryOutcomeStore,
    InMemoryProductGovernance,
    InMemoryVulnerabilityAlertStore,
]:
    outcome_store = InMemoryOutcomeStore()
    governance_store = InMemoryProductGovernance()
    alert_store = InMemoryVulnerabilityAlertStore()
    reporter = ConsumerDutyReporter(outcome_store, governance_store, alert_store)
    return reporter, outcome_store, governance_store, alert_store


# ── generate_annual_report tests (BT-005 resolved) ───────────────────────────


def test_generate_annual_report_returns_dict() -> None:
    """BT-005: generate_annual_report returns dict (no longer raises)."""
    reporter, _, _, _ = make_reporter()
    result = reporter.generate_annual_report(2026)
    assert isinstance(result, dict)


def test_generate_annual_report_has_assessment_year() -> None:
    """BT-005: result contains the requested assessment_year."""
    reporter, _, _, _ = make_reporter()
    result = reporter.generate_annual_report(2026)
    assert result["assessment_year"] == 2026


def test_generate_annual_report_year_preserved() -> None:
    """BT-005: year is preserved correctly for different input years."""
    reporter, _, _, _ = make_reporter()
    assert reporter.generate_annual_report(2024)["assessment_year"] == 2024
    assert reporter.generate_annual_report(2025)["assessment_year"] == 2025


def test_generate_annual_report_has_regulatory_ref() -> None:
    """BT-005: result references PS22/9 s.1.4 regulatory basis."""
    reporter, _, _, _ = make_reporter()
    result = reporter.generate_annual_report(2026)
    assert result["regulatory_ref"] == "PS22/9 s.1.4"


def test_generate_annual_report_has_outcome_summary() -> None:
    """BT-005: result includes outcome_summary from dashboard."""
    reporter, _, _, _ = make_reporter()
    result = reporter.generate_annual_report(2026)
    assert "outcome_summary" in result
    assert isinstance(result["outcome_summary"], dict)


def test_generate_annual_report_has_generated_at() -> None:
    """BT-005: result includes generated_at timestamp."""
    reporter, _, _, _ = make_reporter()
    result = reporter.generate_annual_report(2026)
    assert "generated_at" in result
    assert isinstance(result["generated_at"], str)


def test_generate_annual_report_pass_when_no_failures() -> None:
    """BT-005: assessment_status is PASS when no failing outcomes."""
    reporter, _, _, _ = make_reporter()
    result = reporter.generate_annual_report(2026)
    assert result["assessment_status"] == "PASS"


def test_generate_annual_report_fail_when_has_failures() -> None:
    """BT-005: assessment_status is FAIL when there are failing outcomes."""
    reporter, outcome_store, _, _ = make_reporter()
    assessor = OutcomeAssessor(outcome_store)
    assessor.assess_outcome("c1", OutcomeType.PRODUCTS_SERVICES, {"score": "0.5"})
    result = reporter.generate_annual_report(2026)
    assert result["assessment_status"] == "FAIL"


def test_generate_annual_report_has_failing_products_count() -> None:
    """BT-005: result includes failing_products_count."""
    reporter, _, _, _ = make_reporter()
    result = reporter.generate_annual_report(2026)
    assert "failing_products_count" in result
    assert result["failing_products_count"] == 0


# ── generate_outcome_dashboard tests ─────────────────────────────────────────


def test_generate_outcome_dashboard_returns_dict() -> None:
    """Test generate_outcome_dashboard returns dict."""
    reporter, _, _, _ = make_reporter()
    dashboard = reporter.generate_outcome_dashboard()
    assert isinstance(dashboard, dict)


def test_generate_outcome_dashboard_has_generated_at() -> None:
    """Test dashboard includes generated_at timestamp."""
    reporter, _, _, _ = make_reporter()
    dashboard = reporter.generate_outcome_dashboard()
    assert "generated_at" in dashboard


def test_generate_outcome_dashboard_has_outcome_areas() -> None:
    """Test dashboard includes all 4 outcome areas."""
    reporter, _, _, _ = make_reporter()
    dashboard = reporter.generate_outcome_dashboard()
    assert "outcome_areas" in dashboard
    outcome_areas = dashboard["outcome_areas"]
    assert str(OutcomeType.PRODUCTS_SERVICES) in outcome_areas


def test_generate_outcome_dashboard_counts_failing() -> None:
    """Test dashboard counts failing outcomes correctly."""
    reporter, outcome_store, _, _ = make_reporter()
    assessor = OutcomeAssessor(outcome_store)
    # Add a failing outcome
    assessor.assess_outcome("c1", OutcomeType.PRODUCTS_SERVICES, {"score": "0.5"})
    dashboard = reporter.generate_outcome_dashboard()
    assert dashboard["total_failing_outcomes"] >= 1


def test_generate_outcome_dashboard_counts_vulnerability_alerts() -> None:
    """Test dashboard counts unreviewed vulnerability alerts."""
    reporter, _, _, alert_store = make_reporter()
    alert = VulnerabilityAlert(
        alert_id="vul_001",
        customer_id="c1",
        vulnerability_flag=VulnerabilityFlag.HIGH,
        trigger="debt_restructure",
        created_at=ts(),
        reviewed_by=None,
    )
    alert_store.append(alert)
    dashboard = reporter.generate_outcome_dashboard()
    assert dashboard["unreviewed_vulnerability_alerts"] == 1


def test_generate_outcome_dashboard_counts_failing_products() -> None:
    """Test dashboard counts failing products."""
    reporter, _, governance_store, _ = make_reporter()
    record = ProductGovernanceRecord(
        record_id="pgr_001",
        product_id="p1",
        product_name="Bad Product",
        target_market="retail",
        fair_value_score=Decimal("0.4"),
        last_review_at=ts(),
        intervention_type=InterventionType.RESTRICT,
    )
    governance_store.append(record)
    dashboard = reporter.generate_outcome_dashboard()
    assert dashboard["failing_products_count"] == 1


def test_generate_outcome_dashboard_has_vulnerability_breakdown() -> None:
    """Test dashboard includes vulnerability breakdown."""
    reporter, _, _, _ = make_reporter()
    dashboard = reporter.generate_outcome_dashboard()
    assert "vulnerability_breakdown" in dashboard


# ── export_board_report tests ─────────────────────────────────────────────────


def test_export_board_report_returns_hitl_proposal() -> None:
    """Test export_board_report returns HITLProposal (I-27)."""
    reporter, _, _, _ = make_reporter()
    proposal = reporter.export_board_report("cfo_001")
    assert isinstance(proposal, HITLProposal)


def test_export_board_report_requires_cfo() -> None:
    """Test export_board_report HITLProposal requires CFO approval."""
    reporter, _, _, _ = make_reporter()
    proposal = reporter.export_board_report("cfo_001")
    assert proposal.requires_approval_from == "CFO"


def test_export_board_report_action() -> None:
    """Test export_board_report HITLProposal has EXPORT_BOARD_REPORT action."""
    reporter, _, _, _ = make_reporter()
    proposal = reporter.export_board_report("cfo_001")
    assert proposal.action == "EXPORT_BOARD_REPORT"


def test_export_board_report_autonomy_l4() -> None:
    """Test export_board_report HITLProposal has L4 autonomy."""
    reporter, _, _, _ = make_reporter()
    proposal = reporter.export_board_report("cfo_001")
    assert proposal.autonomy_level == "L4"
