"""Tests for FOS Escalation (IL-FOS-01)."""

from __future__ import annotations

import pytest

from services.complaints.fos_escalation import (
    FOS_DEADLINE_WEEKS,
    FOS_PREPARATION_TRIGGER_WEEKS,
    FOSEscalation,
    FOSHITLProposal,
    InMemoryFOSCaseStore,
)
from services.complaints.fos_models import FOSCaseStatus


def _make_fos() -> FOSEscalation:
    return FOSEscalation(InMemoryFOSCaseStore())


class TestFOSEscalationPrepare:
    def test_prepare_case_returns_package(self):
        fos = _make_fos()
        pkg = fos.prepare_case("CMP001", "CUST001", weeks_elapsed=4)
        assert pkg.case_id.startswith("fos_")
        assert pkg.complaint_id == "CMP001"

    def test_prepare_at_week6_status_ready(self):
        fos = _make_fos()
        pkg = fos.prepare_case("CMP001", "CUST001", weeks_elapsed=6)
        assert pkg.status == FOSCaseStatus.READY

    def test_prepare_before_week6_status_preparing(self):
        fos = _make_fos()
        pkg = fos.prepare_case("CMP001", "CUST001", weeks_elapsed=3)
        assert pkg.status == FOSCaseStatus.PREPARING

    def test_prepare_case_has_timeline(self):
        fos = _make_fos()
        pkg = fos.prepare_case("CMP001", "CUST001", weeks_elapsed=5)
        assert pkg.timeline is not None
        assert pkg.timeline.weeks_elapsed == 5

    def test_prepare_case_has_firm_final_response(self):
        fos = _make_fos()
        pkg = fos.prepare_case("CMP001", "CUST001", weeks_elapsed=7, firm_decision="upheld")
        assert pkg.firm_final_response is not None
        assert pkg.firm_final_response.decision == "upheld"

    def test_prepare_case_has_customer_statement(self):
        fos = _make_fos()
        pkg = fos.prepare_case("CMP001", "CUST001", weeks_elapsed=5)
        assert pkg.customer_statement is not None
        assert pkg.customer_statement.customer_id == "CUST001"

    def test_case_log_append_only(self):
        """I-24: case_log grows."""
        fos = _make_fos()
        fos.prepare_case("CMP001", "CUST001", weeks_elapsed=4)
        fos.prepare_case("CMP002", "CUST002", weeks_elapsed=7)
        assert len(fos.case_log) == 2

    def test_case_id_unique(self):
        fos = _make_fos()
        pkg1 = fos.prepare_case("CMP001", "CUST001", weeks_elapsed=4)
        pkg2 = fos.prepare_case("CMP002", "CUST002", weeks_elapsed=4)
        assert pkg1.case_id != pkg2.case_id

    def test_week6_flagged_returned(self):
        fos = _make_fos()
        fos.prepare_case("CMP001", "CUST001", weeks_elapsed=6)
        fos.prepare_case("CMP002", "CUST002", weeks_elapsed=3)
        flagged = fos.get_week6_flagged()
        assert len(flagged) == 1
        assert flagged[0].complaint_id == "CMP001"

    def test_week8_also_flagged(self):
        fos = _make_fos()
        fos.prepare_case("CMP001", "CUST001", weeks_elapsed=8)
        flagged = fos.get_week6_flagged()
        assert len(flagged) == 1

    def test_fos_constants(self):
        assert FOS_DEADLINE_WEEKS == 8
        assert FOS_PREPARATION_TRIGGER_WEEKS == 6

    def test_prepare_with_custom_events(self):
        fos = _make_fos()
        events = [{"date": "2026-01-01", "description": "Complaint filed"}]
        pkg = fos.prepare_case("CMP001", "CUST001", weeks_elapsed=5, complaint_events=events)
        assert pkg.timeline.events[0]["description"] == "Complaint filed"


class TestFOSEscalationSubmit:
    def test_submit_always_returns_hitl(self):
        """I-27: FOS submission always requires dual sign-off."""
        fos = _make_fos()
        result = fos.submit_case("fos_case_001")
        assert isinstance(result, FOSHITLProposal)

    def test_hitl_not_auto_approved(self):
        """I-27: proposals start unapproved."""
        fos = _make_fos()
        result = fos.submit_case("fos_case_001")
        assert isinstance(result, FOSHITLProposal)
        assert result.approved is False

    def test_hitl_requires_dual_sign_off(self):
        """I-27: requires COMPLAINTS_OFFICER AND HEAD_OF_COMPLIANCE."""
        fos = _make_fos()
        result = fos.submit_case("fos_case_001")
        assert isinstance(result, FOSHITLProposal)
        assert "COMPLAINTS_OFFICER" in result.requires_approval_from
        assert "HEAD_OF_COMPLIANCE" in result.requires_approval_from

    def test_bt011_portal_submit_raises(self):
        """BT-011: FOS portal API is a stub."""
        fos = _make_fos()
        pkg = fos.prepare_case("CMP001", "CUST001", weeks_elapsed=6)
        with pytest.raises(NotImplementedError, match="BT-011"):
            fos.fos_portal_submit(pkg)

    def test_proposals_accumulate(self):
        fos = _make_fos()
        fos.submit_case("case_001")
        fos.submit_case("case_002")
        assert len(fos.proposals) == 2

    def test_store_list_all(self):
        store = InMemoryFOSCaseStore()
        fos = FOSEscalation(store)
        fos.prepare_case("CMP001", "CUST001", weeks_elapsed=5)
        fos.prepare_case("CMP002", "CUST002", weeks_elapsed=7)
        all_cases = store.list_all()
        assert len(all_cases) == 2

    def test_case_status_values(self):
        assert FOSCaseStatus.PREPARING == "PREPARING"
        assert FOSCaseStatus.SUBMITTED == "SUBMITTED"
        assert FOSCaseStatus.RESOLVED == "RESOLVED"

    def test_case_weeks_stored_correctly(self):
        fos = _make_fos()
        pkg = fos.prepare_case("CMP001", "CUST001", weeks_elapsed=7)
        assert pkg.weeks_since_complaint == 7

    def test_list_all_returns_latest_per_case(self):
        """Append-only: list_all returns latest state per case_id."""
        store = InMemoryFOSCaseStore()
        fos = FOSEscalation(store)
        fos.prepare_case("CMP001", "CUST001", weeks_elapsed=4)
        all_cases = store.list_all()
        assert len(all_cases) == 1

    def test_timeline_complaint_id_matches(self):
        fos = _make_fos()
        pkg = fos.prepare_case("CMP_XYZ", "CUST001", weeks_elapsed=5)
        assert pkg.timeline.complaint_id == "CMP_XYZ"

    def test_firm_response_not_none_after_prepare(self):
        fos = _make_fos()
        pkg = fos.prepare_case("CMP001", "CUST001", weeks_elapsed=5)
        assert pkg.firm_final_response is not None

    def test_prepare_at_week_5_not_flagged(self):
        fos = _make_fos()
        fos.prepare_case("CMP001", "CUST001", weeks_elapsed=5)
        flagged = fos.get_week6_flagged()
        assert len(flagged) == 0
