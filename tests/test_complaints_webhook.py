"""
test_complaints_webhook.py — FastAPI endpoint tests for ComplaintsWebhook
IL-022 | FCA Consumer Duty DISP | banxe-emi-stack
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from services.complaints.complaint_service import (
    SLABreach,
    SLAWarning,
)
from services.complaints.n8n_webhook import app


# ─── Stub ComplaintService ────────────────────────────────────────────────────

class StubComplaintService:
    def __init__(self, complaint_id="test-uuid-1234"):
        self._complaint_id = complaint_id
        self.opened = []
        self.resolved = []
        self.escalated = []

    def open_complaint(self, customer_id, category, description,
                       channel="API", created_by="system") -> str:
        self.opened.append((customer_id, category, description))
        return self._complaint_id

    def resolve_complaint(self, complaint_id, resolution_summary, actor="system"):
        self.resolved.append((complaint_id, resolution_summary))

    def check_sla_breaches(self) -> List[SLABreach]:
        return []

    def check_sla_warnings(self) -> List[SLAWarning]:
        return []

    def escalate_to_fos(self, complaint_id, fos_reference="", actor="system"):
        self.escalated.append((complaint_id, fos_reference))


class StubServiceWithBreaches(StubComplaintService):
    def check_sla_breaches(self):
        now = datetime.now(timezone.utc)
        return [
            SLABreach(
                complaint_id="breach-001",
                customer_id="cust-999",
                category="PAYMENT",
                created_at=now - timedelta(days=60),
                sla_deadline=now - timedelta(days=4),
                days_overdue=4,
            )
        ]

    def check_sla_warnings(self):
        now = datetime.now(timezone.utc)
        return [
            SLAWarning(
                complaint_id="warn-001",
                customer_id="cust-888",
                sla_deadline=now + timedelta(days=3),
                days_remaining=3,
            )
        ]


# ─── Tests ────────────────────────────────────────────────────────────────────

@pytest.fixture
def stub_svc():
    return StubComplaintService()


@pytest.fixture
def client_with_stub(stub_svc):
    with patch("services.complaints.n8n_webhook._get_service", return_value=stub_svc):
        yield TestClient(app)


class TestHealthEndpoint:
    def test_health_returns_ok(self, client_with_stub):
        resp = client_with_stub.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestCreateComplaint:
    def test_post_new_complaint_201(self, client_with_stub, stub_svc):
        resp = client_with_stub.post("/complaints/new", json={
            "customer_id": "cust-100",
            "category": "PAYMENT",
            "description": "My payment was not processed after 3 days",
            "channel": "API",
        })
        assert resp.status_code == 201
        body = resp.json()
        assert "complaint_id" in body
        assert "sla_deadline" in body
        assert "8 weeks" in body["message"]

    def test_complaint_forwarded_to_service(self, client_with_stub, stub_svc):
        client_with_stub.post("/complaints/new", json={
            "customer_id": "cust-101",
            "category": "FRAUD",
            "description": "Unauthorised transaction on my account",
        })
        assert len(stub_svc.opened) == 1
        assert stub_svc.opened[0][0] == "cust-101"
        assert stub_svc.opened[0][1] == "FRAUD"

    def test_invalid_category_422(self, client_with_stub):
        resp = client_with_stub.post("/complaints/new", json={
            "customer_id": "cust-102",
            "category": "INVALID_CAT",
            "description": "Test complaint",
        })
        assert resp.status_code == 422

    def test_description_too_short_422(self, client_with_stub):
        resp = client_with_stub.post("/complaints/new", json={
            "customer_id": "cust-103",
            "category": "SERVICE",
            "description": "short",  # < 10 chars
        })
        assert resp.status_code == 422

    def test_invalid_channel_422(self, client_with_stub):
        resp = client_with_stub.post("/complaints/new", json={
            "customer_id": "cust-104",
            "category": "ACCOUNT",
            "description": "Account issue reported",
            "channel": "CARRIER_PIGEON",
        })
        assert resp.status_code == 422


class TestSLACheck:
    def test_no_breaches_no_warnings(self, client_with_stub):
        resp = client_with_stub.get("/complaints/sla-check")
        assert resp.status_code == 200
        body = resp.json()
        assert body["breaches"] == 0
        assert body["warnings"] == 0
        assert body["breach_ids"] == []

    def test_returns_breach_and_warning_counts(self, stub_svc):
        breach_svc = StubServiceWithBreaches()
        with patch("services.complaints.n8n_webhook._get_service", return_value=breach_svc):
            client = TestClient(app)
            resp = client.get("/complaints/sla-check")
        assert resp.status_code == 200
        body = resp.json()
        assert body["breaches"] == 1
        assert body["warnings"] == 1
        assert "breach-001" in body["breach_ids"]
        assert "warn-001" in body["warning_ids"]


class TestResolveComplaint:
    def test_resolve_returns_200(self, client_with_stub, stub_svc):
        resp = client_with_stub.post("/complaints/cid-001/resolve", json={
            "resolution_summary": "Issue investigated and refund issued to customer account",
            "actor": "mlro-001",
        })
        assert resp.status_code == 200
        assert resp.json()["resolved"] is True

    def test_resolve_calls_service(self, client_with_stub, stub_svc):
        client_with_stub.post("/complaints/cid-002/resolve", json={
            "resolution_summary": "Complaint resolved following internal review",
        })
        assert len(stub_svc.resolved) == 1
        assert stub_svc.resolved[0][0] == "cid-002"


class TestFosEscalation:
    def test_escalate_returns_200(self, client_with_stub):
        resp = client_with_stub.post("/complaints/cid-003/escalate-fos", json={
            "fos_reference": "FOS-2026-001",
            "actor": "cco-001",
        })
        assert resp.status_code == 200
        assert resp.json()["escalated"] is True

    def test_escalate_calls_service(self, client_with_stub, stub_svc):
        client_with_stub.post("/complaints/cid-004/escalate-fos", json={
            "fos_reference": "FOS-2026-002",
        })
        assert len(stub_svc.escalated) == 1
        assert stub_svc.escalated[0][0] == "cid-004"
        assert stub_svc.escalated[0][1] == "FOS-2026-002"
