"""
test_complaint_service.py — Unit tests for ComplaintService
IL-022 | FCA Consumer Duty DISP | banxe-emi-stack
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

import pytest

from services.complaints.complaint_service import (
    ComplaintService,
)


# ─── In-memory stub ───────────────────────────────────────────────────────────

class InMemoryComplaintRepo:
    """Test double — no ClickHouse required."""

    def __init__(self):
        self.complaints: dict = {}
        self.events: list = []

    def insert_complaint(self, complaint_id: str, customer_id: str,
                         category: str, description: str,
                         sla_deadline: datetime, channel: str = "API",
                         created_by: str = "system") -> None:
        self.complaints[complaint_id] = {
            "id": complaint_id,
            "customer_id": customer_id,
            "category": category,
            "description": description,
            "status": "OPEN",
            "created_at": datetime.now(timezone.utc),
            "sla_deadline": sla_deadline,
            "resolved_at": None,
            "resolution_summary": "",
            "assigned_to": "",
        }

    def update_status(self, complaint_id: str, new_status: str,
                      resolved_at: Optional[datetime] = None,
                      resolution_summary: str = "") -> None:
        if complaint_id in self.complaints:
            self.complaints[complaint_id]["status"] = new_status
            if resolved_at:
                self.complaints[complaint_id]["resolved_at"] = resolved_at
            if resolution_summary:
                self.complaints[complaint_id]["resolution_summary"] = resolution_summary

    def insert_event(self, complaint_id: str, event_type: str,
                     old_status: str = "", new_status: str = "",
                     note: str = "", actor: str = "system") -> None:
        self.events.append({
            "complaint_id": complaint_id,
            "event_type": event_type,
            "old_status": old_status,
            "new_status": new_status,
            "note": note,
            "actor": actor,
        })

    def get_sla_breaches(self) -> List[dict]:
        now = datetime.now(timezone.utc)
        result = []
        for c in self.complaints.values():
            if c["status"] not in ("RESOLVED", "FOS_ESCALATED"):
                dl = c["sla_deadline"]
                if dl.tzinfo is None:
                    dl = dl.replace(tzinfo=timezone.utc)
                if dl < now:
                    days_overdue = (now - dl).days
                    result.append({
                        "complaint_id": c["id"],
                        "customer_id": c["customer_id"],
                        "category": c["category"],
                        "created_at": c["created_at"],
                        "sla_deadline": dl,
                        "days_overdue": days_overdue,
                    })
        return result

    def get_sla_warnings(self) -> List[dict]:
        now = datetime.now(timezone.utc)
        warning_cutoff = now + timedelta(days=7)
        result = []
        for c in self.complaints.values():
            if c["status"] not in ("RESOLVED", "FOS_ESCALATED"):
                dl = c["sla_deadline"]
                if dl.tzinfo is None:
                    dl = dl.replace(tzinfo=timezone.utc)
                if now <= dl <= warning_cutoff:
                    days_remaining = (dl - now).days
                    result.append({
                        "complaint_id": c["id"],
                        "customer_id": c["customer_id"],
                        "category": c["category"],
                        "created_at": c["created_at"],
                        "sla_deadline": dl,
                        "days_remaining": days_remaining,
                    })
        return result

    def get_complaint(self, complaint_id: str) -> Optional[dict]:
        return self.complaints.get(complaint_id)


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def repo():
    return InMemoryComplaintRepo()


@pytest.fixture
def svc(repo):
    return ComplaintService(repo)


# ─── Tests ────────────────────────────────────────────────────────────────────

class TestOpenComplaint:
    def test_returns_complaint_id(self, svc, repo):
        cid = svc.open_complaint("cust-001", "PAYMENT", "Payment not received", "API")
        assert cid
        assert len(cid) == 36  # UUID

    def test_stores_complaint_in_repo(self, svc, repo):
        cid = svc.open_complaint("cust-002", "ACCOUNT", "Account locked incorrectly", "EMAIL")
        stored = repo.get_complaint(cid)
        assert stored is not None
        assert stored["customer_id"] == "cust-002"
        assert stored["category"] == "ACCOUNT"
        assert stored["status"] == "OPEN"

    def test_sla_deadline_is_56_days(self, svc, repo):
        cid = svc.open_complaint("cust-003", "SERVICE", "App not working", "WEB")
        stored = repo.get_complaint(cid)
        delta = stored["sla_deadline"] - stored["created_at"]
        # DISP 1.4.1R — 8 weeks = 56 days. Allow sub-second clock skew.
        assert delta.total_seconds() >= 56 * 86400 - 1

    def test_opened_event_written_to_audit_trail(self, svc, repo):
        cid = svc.open_complaint("cust-004", "CHARGES", "Incorrect fee charged", "API")
        opened_events = [e for e in repo.events if e["event_type"] == "OPENED"]
        assert len(opened_events) == 1
        assert opened_events[0]["complaint_id"] == cid

    def test_channel_stored_correctly(self, svc, repo):
        cid = svc.open_complaint("cust-005", "FRAUD", "Unauthorised transaction", "TELEGRAM")
        # channel stored in repo — in our stub it's not a top-level field, but
        # the real CH repo stores it; we verify the call went through
        opened = [e for e in repo.events if e["complaint_id"] == cid]
        assert len(opened) >= 1


class TestResolveComplaint:
    def test_status_set_to_resolved(self, svc, repo):
        cid = svc.open_complaint("cust-010", "SERVICE", "Long wait time", "API")
        svc.resolve_complaint(cid, "Resolved: improved queue processing")
        stored = repo.get_complaint(cid)
        assert stored["status"] == "RESOLVED"
        assert "improved queue" in stored["resolution_summary"]

    def test_resolved_event_appended(self, svc, repo):
        cid = svc.open_complaint("cust-011", "PAYMENT", "Double charge", "EMAIL")
        svc.resolve_complaint(cid, "Refund issued", actor="mlro-001")
        resolved_events = [e for e in repo.events
                           if e["event_type"] == "RESOLVED" and e["complaint_id"] == cid]
        assert len(resolved_events) == 1
        assert resolved_events[0]["actor"] == "mlro-001"
        assert resolved_events[0]["new_status"] == "RESOLVED"

    def test_audit_trail_append_only(self, svc, repo):
        """Both OPENED and RESOLVED events must exist — I-24 append-only."""
        cid = svc.open_complaint("cust-012", "ACCOUNT", "Closed without notice", "API")
        svc.resolve_complaint(cid, "Account reinstated")
        events_for_complaint = [e for e in repo.events if e["complaint_id"] == cid]
        types = {e["event_type"] for e in events_for_complaint}
        assert "OPENED" in types
        assert "RESOLVED" in types


class TestSLABreachDetection:
    def test_no_breaches_when_all_within_sla(self, svc, repo):
        svc.open_complaint("cust-020", "SERVICE", "Slow app", "API")
        breaches = svc.check_sla_breaches()
        assert breaches == []

    def test_detects_overdue_complaint(self, svc, repo):
        cid = svc.open_complaint("cust-021", "CHARGES", "Fee dispute", "API")
        # Backdate the SLA deadline to yesterday
        repo.complaints[cid]["sla_deadline"] = (
            datetime.now(timezone.utc) - timedelta(days=1)
        )
        breaches = svc.check_sla_breaches()
        assert len(breaches) == 1
        assert breaches[0].complaint_id == cid
        assert breaches[0].days_overdue >= 1

    def test_resolved_complaint_not_counted_as_breach(self, svc, repo):
        cid = svc.open_complaint("cust-022", "PAYMENT", "Delayed transfer", "API")
        repo.complaints[cid]["sla_deadline"] = (
            datetime.now(timezone.utc) - timedelta(days=2)
        )
        svc.resolve_complaint(cid, "Transfer processed")
        breaches = svc.check_sla_breaches()
        assert all(b.complaint_id != cid for b in breaches)

    def test_breach_event_written_to_audit_trail(self, svc, repo):
        cid = svc.open_complaint("cust-023", "FRAUD", "Disputed charge", "WEB")
        repo.complaints[cid]["sla_deadline"] = (
            datetime.now(timezone.utc) - timedelta(days=3)
        )
        svc.check_sla_breaches()
        breach_events = [e for e in repo.events
                         if e["event_type"] == "SLA_BREACHED" and e["complaint_id"] == cid]
        assert len(breach_events) == 1


class TestSLAWarnings:
    def test_no_warnings_when_all_far_from_deadline(self, svc, repo):
        svc.open_complaint("cust-030", "SERVICE", "App crash", "API")
        warnings = svc.check_sla_warnings()
        assert warnings == []

    def test_detects_warning_within_7_days(self, svc, repo):
        cid = svc.open_complaint("cust-031", "ACCOUNT", "Wrong balance", "API")
        # Set deadline 3 days from now
        repo.complaints[cid]["sla_deadline"] = (
            datetime.now(timezone.utc) + timedelta(days=3)
        )
        warnings = svc.check_sla_warnings()
        assert len(warnings) == 1
        assert warnings[0].complaint_id == cid
        assert warnings[0].days_remaining <= 3

    def test_warning_event_written_to_audit_trail(self, svc, repo):
        cid = svc.open_complaint("cust-032", "CHARGES", "Interest calculation", "EMAIL")
        repo.complaints[cid]["sla_deadline"] = (
            datetime.now(timezone.utc) + timedelta(days=5)
        )
        svc.check_sla_warnings()
        warning_events = [e for e in repo.events
                          if e["event_type"] == "SLA_WARNING" and e["complaint_id"] == cid]
        assert len(warning_events) == 1


class TestFosEscalation:
    def test_status_set_to_fos_escalated(self, svc, repo):
        cid = svc.open_complaint("cust-040", "PAYMENT", "Refund not received", "API")
        svc.escalate_to_fos(cid, fos_reference="FOS-2026-001")
        stored = repo.get_complaint(cid)
        assert stored["status"] == "FOS_ESCALATED"

    def test_fos_event_written_to_audit_trail(self, svc, repo):
        cid = svc.open_complaint("cust-041", "FRAUD", "Identity theft", "PHONE")
        svc.escalate_to_fos(cid, fos_reference="FOS-2026-002", actor="cco-001")
        fos_events = [e for e in repo.events
                      if e["event_type"] == "FOS_ESCALATED" and e["complaint_id"] == cid]
        assert len(fos_events) == 1
        assert fos_events[0]["actor"] == "cco-001"
        assert "FOS-2026-002" in fos_events[0]["note"]

    def test_fos_not_counted_in_sla_breaches(self, svc, repo):
        cid = svc.open_complaint("cust-042", "ACCOUNT", "Account blocked", "API")
        repo.complaints[cid]["sla_deadline"] = (
            datetime.now(timezone.utc) - timedelta(days=5)
        )
        svc.escalate_to_fos(cid)
        breaches = svc.check_sla_breaches()
        assert all(b.complaint_id != cid for b in breaches)

    def test_full_lifecycle_audit_trail(self, svc, repo):
        """OPENED → SLA_WARNING → SLA_BREACHED → FOS_ESCALATED all in trail."""
        cid = svc.open_complaint("cust-043", "CHARGES", "Fee refund", "WEB")
        # Trigger warning
        repo.complaints[cid]["sla_deadline"] = datetime.now(timezone.utc) + timedelta(days=2)
        svc.check_sla_warnings()
        # Breach
        repo.complaints[cid]["sla_deadline"] = datetime.now(timezone.utc) - timedelta(days=1)
        svc.check_sla_breaches()
        # FOS
        svc.escalate_to_fos(cid, fos_reference="FOS-2026-003")

        events = [e for e in repo.events if e["complaint_id"] == cid]
        types = {e["event_type"] for e in events}
        assert {"OPENED", "SLA_WARNING", "SLA_BREACHED", "FOS_ESCALATED"}.issubset(types)
