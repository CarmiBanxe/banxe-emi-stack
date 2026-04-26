"""Tests for FCA DISP Complaints (IL-DSP-01)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.complaints.complaints_engine import (
    REDRESS_HITL_THRESHOLD,
    ComplaintsEngine,
    InMemoryComplaintStore,
)
from services.complaints.complaints_models import (
    ComplaintCategory,
    ComplaintStatus,
    Resolution,
)


def _make_engine() -> ComplaintsEngine:
    return ComplaintsEngine(InMemoryComplaintStore())


class TestComplaintsEngine:
    def test_register_returns_complaint(self):
        engine = _make_engine()
        c = engine.register("CUST001", ComplaintCategory.SERVICE_QUALITY, "Test complaint")
        assert c.complaint_id is not None
        assert c.status == ComplaintStatus.REGISTERED

    def test_register_service_quality_sla_15(self):
        engine = _make_engine()
        c = engine.register("CUST001", ComplaintCategory.SERVICE_QUALITY, "desc")
        assert c.sla_days == 15

    def test_register_fraud_scam_sla_35(self):
        engine = _make_engine()
        c = engine.register("CUST001", ComplaintCategory.FRAUD_SCAM, "desc")
        assert c.sla_days == 35

    def test_register_account_access_sla_35(self):
        engine = _make_engine()
        c = engine.register("CUST001", ComplaintCategory.ACCOUNT_ACCESS, "desc")
        assert c.sla_days == 35

    def test_acknowledge_updates_status(self):
        engine = _make_engine()
        c = engine.register("CUST001", ComplaintCategory.SERVICE_QUALITY, "desc")
        updated = engine.acknowledge(c.complaint_id)
        assert updated is not None
        assert updated.status == ComplaintStatus.ACKNOWLEDGED

    def test_acknowledge_unknown_returns_none(self):
        engine = _make_engine()
        result = engine.acknowledge("UNKNOWN_ID")
        assert result is None

    def test_investigate_returns_report(self):
        engine = _make_engine()
        c = engine.register("CUST001", ComplaintCategory.FEES_CHARGES, "Wrong fees")
        report = engine.investigate(c.complaint_id, "Agent Smith", "Fee calculation error found")
        assert report.complaint_id == c.complaint_id
        assert report.investigator == "Agent Smith"

    def test_resolve_returns_resolution(self):
        engine = _make_engine()
        c = engine.register("CUST001", ComplaintCategory.SERVICE_QUALITY, "desc")
        res = engine.resolve(c.complaint_id, "upheld", "100.00")
        assert res.outcome == "upheld"
        assert res.redress_amount == "100.00"

    def test_redress_amount_is_decimal_string(self):
        engine = _make_engine()
        c = engine.register("CUST001", ComplaintCategory.SERVICE_QUALITY, "desc")
        res = engine.resolve(c.complaint_id, "upheld", "250.00")
        # Must be parseable as Decimal (I-01)
        assert isinstance(res.redress_amount, str)
        Decimal(res.redress_amount)

    def test_redress_negative_raises(self):
        with pytest.raises(ValueError):
            Resolution(
                complaint_id="CMP001",
                outcome="upheld",
                redress_amount="-10.00",
                resolved_at="2026-04-22T10:00:00+00:00",
            )

    def test_resolutions_append_only(self):
        """I-24: resolutions grow."""
        engine = _make_engine()
        c1 = engine.register("CUST001", ComplaintCategory.SERVICE_QUALITY, "desc1")
        c2 = engine.register("CUST002", ComplaintCategory.FEES_CHARGES, "desc2")
        engine.resolve(c1.complaint_id, "upheld", "50.00")
        engine.resolve(c2.complaint_id, "not_upheld", "0.00")
        assert len(engine.resolutions) == 2

    def test_audit_log_append_only(self):
        """I-24: audit log grows."""
        engine = _make_engine()
        c = engine.register("CUST001", ComplaintCategory.SERVICE_QUALITY, "desc")
        engine.acknowledge(c.complaint_id)
        assert len(engine.audit_log) >= 2

    def test_escalate_to_fos_raises_bt010(self):
        """BT-010: FOS escalation is a stub."""
        engine = _make_engine()
        with pytest.raises(NotImplementedError, match="BT-010"):
            engine.escalate_to_fos("CMP001")

    def test_get_sla_approaching_returns_open(self):
        engine = _make_engine()
        engine.register("CUST001", ComplaintCategory.SERVICE_QUALITY, "desc")
        approaching = engine.get_sla_approaching()
        assert len(approaching) >= 1

    def test_complaint_id_starts_with_cmp(self):
        engine = _make_engine()
        c = engine.register("CUST001", ComplaintCategory.SERVICE_QUALITY, "desc")
        assert c.complaint_id.startswith("cmp_")

    def test_redress_threshold_is_decimal(self):
        assert isinstance(REDRESS_HITL_THRESHOLD, Decimal)
        assert Decimal("500.00") == REDRESS_HITL_THRESHOLD

    def test_complaint_categories(self):
        assert ComplaintCategory.SERVICE_QUALITY == "service_quality"
        assert ComplaintCategory.FRAUD_SCAM == "fraud_scam"

    def test_complaint_status_flow(self):
        assert ComplaintStatus.REGISTERED == "REGISTERED"
        assert ComplaintStatus.RESOLVED == "RESOLVED"
        assert ComplaintStatus.ESCALATED == "ESCALATED"


class TestComplaintsAgent:
    def test_small_redress_resolved_directly(self):
        from services.complaints.complaints_agent import ComplaintsAgent

        engine = _make_engine()
        agent = ComplaintsAgent(engine)
        c = engine.register("CUST001", ComplaintCategory.SERVICE_QUALITY, "desc")
        result = agent.resolve_with_redress(c.complaint_id, "upheld", "200.00")
        assert isinstance(result, Resolution)

    def test_large_redress_returns_hitl(self):
        """I-27: redress > £500 requires COMPLAINTS_OFFICER."""
        from services.complaints.complaints_agent import ComplaintsAgent, ComplaintsHITLProposal

        engine = _make_engine()
        agent = ComplaintsAgent(engine)
        c = engine.register("CUST001", ComplaintCategory.FRAUD_SCAM, "desc")
        result = agent.resolve_with_redress(c.complaint_id, "upheld", "501.00")
        assert isinstance(result, ComplaintsHITLProposal)

    def test_hitl_not_auto_approved(self):
        """I-27: proposals start unapproved."""
        from services.complaints.complaints_agent import ComplaintsAgent, ComplaintsHITLProposal

        engine = _make_engine()
        agent = ComplaintsAgent(engine)
        c = engine.register("CUST001", ComplaintCategory.SERVICE_QUALITY, "desc")
        result = agent.resolve_with_redress(c.complaint_id, "upheld", "1000.00")
        assert isinstance(result, ComplaintsHITLProposal)
        assert result.approved is False

    def test_hitl_requires_complaints_officer(self):
        from services.complaints.complaints_agent import ComplaintsAgent, ComplaintsHITLProposal

        engine = _make_engine()
        agent = ComplaintsAgent(engine)
        c = engine.register("CUST001", ComplaintCategory.SERVICE_QUALITY, "desc")
        result = agent.resolve_with_redress(c.complaint_id, "upheld", "999.99")
        assert isinstance(result, ComplaintsHITLProposal)
        assert result.requires_approval_from == "COMPLAINTS_OFFICER"

    def test_exactly_at_threshold_resolves_directly(self):
        """£500.00 exactly is NOT above threshold."""
        from services.complaints.complaints_agent import ComplaintsAgent

        engine = _make_engine()
        agent = ComplaintsAgent(engine)
        c = engine.register("CUST001", ComplaintCategory.SERVICE_QUALITY, "desc")
        result = agent.resolve_with_redress(c.complaint_id, "upheld", "500.00")
        assert isinstance(result, Resolution)

    def test_proposals_accumulate(self):
        from services.complaints.complaints_agent import ComplaintsAgent

        engine = _make_engine()
        agent = ComplaintsAgent(engine)
        c1 = engine.register("CUST001", ComplaintCategory.SERVICE_QUALITY, "d1")
        c2 = engine.register("CUST002", ComplaintCategory.FRAUD_SCAM, "d2")
        agent.resolve_with_redress(c1.complaint_id, "upheld", "600.00")
        agent.resolve_with_redress(c2.complaint_id, "upheld", "700.00")
        assert len(agent.proposals) == 2
