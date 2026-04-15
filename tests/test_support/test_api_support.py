"""
tests/test_support/test_api_support.py
IL-CSB-01 | #118 | banxe-emi-stack — FastAPI support router tests
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


# ─── POST /v1/support/tickets ────────────────────────────────────────────────


def test_create_ticket_returns_201() -> None:
    resp = client.post(
        "/v1/support/tickets",
        json={
            "customer_id": "cust-api-001",
            "subject": "Payment is stuck",
            "body": "My FPS transfer has been stuck in pending for 3 hours",
        },
    )
    assert resp.status_code == 201


def test_create_ticket_response_has_id() -> None:
    resp = client.post(
        "/v1/support/tickets",
        json={
            "customer_id": "cust-api-001",
            "subject": "Account locked",
            "body": "I cannot login to my account and my card is locked",
        },
    )
    data = resp.json()
    assert "id" in data
    assert len(data["id"]) == 36


def test_create_ticket_sla_deadline_present() -> None:
    resp = client.post(
        "/v1/support/tickets",
        json={
            "customer_id": "cust-api-002",
            "subject": "KYC document issue",
            "body": "My identity verification document was rejected, what should I do",
        },
    )
    data = resp.json()
    assert "sla_deadline" in data
    assert data["sla_deadline"] is not None


def test_create_ticket_fraud_gets_critical_priority() -> None:
    resp = client.post(
        "/v1/support/tickets",
        json={
            "customer_id": "cust-api-003",
            "subject": "Fraud on my account",
            "body": "There is an unauthorized transaction on my account, this is fraud",
        },
    )
    data = resp.json()
    assert data["priority"] == "CRITICAL"


def test_create_ticket_subject_too_short_returns_422() -> None:
    resp = client.post(
        "/v1/support/tickets",
        json={
            "customer_id": "cust-api-001",
            "subject": "Hi",
            "body": "Short subject should fail validation",
        },
    )
    assert resp.status_code == 422


def test_create_ticket_body_too_short_returns_422() -> None:
    resp = client.post(
        "/v1/support/tickets",
        json={
            "customer_id": "cust-api-001",
            "subject": "Valid subject line",
            "body": "Short",
        },
    )
    assert resp.status_code == 422


# ─── GET /v1/support/tickets ──────────────────────────────────────────────────


def test_list_tickets_returns_200() -> None:
    resp = client.get("/v1/support/tickets")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_list_tickets_filter_by_customer_id() -> None:
    # Create tickets for two customers
    client.post(
        "/v1/support/tickets",
        json={
            "customer_id": "filter-cust-X",
            "subject": "Ticket for customer X",
            "body": "This is a ticket for customer X to test filtering",
        },
    )
    client.post(
        "/v1/support/tickets",
        json={
            "customer_id": "filter-cust-Y",
            "subject": "Ticket for customer Y",
            "body": "This is a ticket for customer Y to test filtering",
        },
    )
    resp = client.get("/v1/support/tickets?customer_id=filter-cust-X")
    data = resp.json()
    assert all(t["customer_id"] == "filter-cust-X" for t in data)


# ─── GET /v1/support/tickets/{id} ────────────────────────────────────────────


def test_get_ticket_by_id_returns_200() -> None:
    create_resp = client.post(
        "/v1/support/tickets",
        json={
            "customer_id": "cust-get-001",
            "subject": "Get ticket test",
            "body": "Testing that get ticket by ID returns the correct ticket",
        },
    )
    ticket_id = create_resp.json()["id"]
    resp = client.get(f"/v1/support/tickets/{ticket_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == ticket_id


def test_get_ticket_nonexistent_returns_404() -> None:
    resp = client.get("/v1/support/tickets/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


# ─── POST /v1/support/tickets/{id}/resolve ───────────────────────────────────


def test_resolve_ticket_returns_200() -> None:
    create_resp = client.post(
        "/v1/support/tickets",
        json={
            "customer_id": "cust-resolve-001",
            "subject": "Resolve test ticket",
            "body": "Testing resolve endpoint with a sufficiently long body text",
        },
    )
    ticket_id = create_resp.json()["id"]
    resp = client.post(
        f"/v1/support/tickets/{ticket_id}/resolve",
        json={
            "resolution_summary": "Issue was resolved by resetting the customer PIN successfully"
        },
    )
    assert resp.status_code == 200


def test_resolve_ticket_status_is_resolved() -> None:
    create_resp = client.post(
        "/v1/support/tickets",
        json={
            "customer_id": "cust-resolve-002",
            "subject": "Resolve status test",
            "body": "Testing that resolved ticket has RESOLVED status in response",
        },
    )
    ticket_id = create_resp.json()["id"]
    resp = client.post(
        f"/v1/support/tickets/{ticket_id}/resolve",
        json={"resolution_summary": "Issue was resolved by the support team in a timely manner"},
    )
    data = resp.json()
    assert data["status"] == "RESOLVED"


def test_resolve_ticket_short_summary_returns_422() -> None:
    create_resp = client.post(
        "/v1/support/tickets",
        json={
            "customer_id": "cust-resolve-003",
            "subject": "Short summary test ticket",
            "body": "Testing that short resolution summary is rejected by validation",
        },
    )
    ticket_id = create_resp.json()["id"]
    resp = client.post(
        f"/v1/support/tickets/{ticket_id}/resolve",
        json={"resolution_summary": "OK"},
    )
    assert resp.status_code == 422


def test_resolve_nonexistent_ticket_returns_404() -> None:
    resp = client.post(
        "/v1/support/tickets/00000000-0000-0000-0000-000000000000/resolve",
        json={"resolution_summary": "Some resolution text that is long enough to pass validation"},
    )
    assert resp.status_code == 404


# ─── GET /v1/support/metrics ─────────────────────────────────────────────────


def test_get_metrics_returns_200() -> None:
    resp = client.get("/v1/support/metrics")
    assert resp.status_code == 200


def test_get_metrics_has_required_fields() -> None:
    resp = client.get("/v1/support/metrics")
    data = resp.json()
    required_fields = [
        "period_days",
        "total_responses",
        "avg_csat",
        "avg_nps",
        "nps_score",
        "nps_promoters",
        "nps_detractors",
        "nps_passives",
        "by_category",
    ]
    for field in required_fields:
        assert field in data, f"Missing field: {field}"


def test_get_metrics_custom_period() -> None:
    resp = client.get("/v1/support/metrics?period_days=7")
    assert resp.status_code == 200
    assert resp.json()["period_days"] == 7


def test_get_metrics_period_too_large_returns_422() -> None:
    resp = client.get("/v1/support/metrics?period_days=400")
    assert resp.status_code == 422


def test_get_metrics_period_0_returns_422() -> None:
    resp = client.get("/v1/support/metrics?period_days=0")
    assert resp.status_code == 422
