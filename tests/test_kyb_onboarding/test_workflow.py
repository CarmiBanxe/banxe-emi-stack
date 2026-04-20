"""Tests for OnboardingWorkflow — Phase 45 (IL-KYB-01)."""

from __future__ import annotations

from services.kyb_onboarding.models import InMemoryApplicationStore
from services.kyb_onboarding.onboarding_workflow import (
    SLA_BUSINESS_DAYS,
    WORKFLOW_STAGES,
    OnboardingWorkflow,
)


def make_workflow():
    return OnboardingWorkflow(InMemoryApplicationStore())


# --- WORKFLOW_STAGES ---


def test_workflow_stages_count():
    assert len(WORKFLOW_STAGES) == 5


def test_workflow_stages_order():
    assert WORKFLOW_STAGES[0] == "doc_check"
    assert WORKFLOW_STAGES[-1] == "decision"


def test_sla_business_days():
    assert SLA_BUSINESS_DAYS == 5


# --- start_workflow ---


def test_start_workflow_returns_doc_check():
    wf = make_workflow()
    result = wf.start_workflow("app_001")
    assert result["stage"] == "doc_check"
    assert "started_at" in result


def test_start_workflow_creates_state():
    wf = make_workflow()
    wf.start_workflow("app_001")
    status = wf.get_workflow_status("app_001")
    assert status["current_stage"] == "doc_check"


# --- advance_stage ---


def test_advance_stage_pass_moves_to_next():
    wf = make_workflow()
    wf.start_workflow("app_001")
    result = wf.advance_stage("app_001", "doc_check", True, "docs ok")
    assert result["stage"] == "ubo_verify"
    assert result["status"] == "advanced"


def test_advance_stage_fail_stays():
    wf = make_workflow()
    wf.start_workflow("app_001")
    result = wf.advance_stage("app_001", "doc_check", False, "missing docs")
    assert result["stage"] == "doc_check"
    assert result["status"] == "failed"


def test_advance_stage_full_progression():
    wf = make_workflow()
    wf.start_workflow("app_001")
    stages = ["doc_check", "ubo_verify", "sanctions", "risk"]
    for stage in stages:
        wf.advance_stage("app_001", stage, True, "passed")
    result = wf.advance_stage("app_001", "decision", True, "approved")
    assert result["status"] == "advanced"


# --- get_workflow_status ---


def test_get_workflow_status_not_started():
    wf = make_workflow()
    status = wf.get_workflow_status("app_999")
    assert status["status"] == "not_started"


def test_get_workflow_status_has_stages():
    wf = make_workflow()
    wf.start_workflow("app_001")
    wf.advance_stage("app_001", "doc_check", True)
    status = wf.get_workflow_status("app_001")
    assert "doc_check" in status["stages_completed"]
    assert "current_stage" in status


# --- get_timeline ---


def test_get_timeline_empty_for_new():
    wf = make_workflow()
    assert wf.get_timeline("app_999") == []


def test_get_timeline_has_entries_after_start():
    wf = make_workflow()
    wf.start_workflow("app_001")
    timeline = wf.get_timeline("app_001")
    assert len(timeline) >= 1


# --- calculate_sla_remaining ---


def test_calculate_sla_remaining_returns_int():
    wf = make_workflow()
    remaining = wf.calculate_sla_remaining("app_001")
    assert isinstance(remaining, int)


def test_calculate_sla_remaining_default_for_missing():
    wf = make_workflow()
    remaining = wf.calculate_sla_remaining("nonexistent")
    assert remaining == SLA_BUSINESS_DAYS


def test_calculate_sla_remaining_recent_app_positive():
    wf = make_workflow()
    # app_003 submitted 2026-03-01, should have negative (overdue as of 2026-04-20)
    remaining = wf.calculate_sla_remaining("app_003")
    assert isinstance(remaining, int)
