"""
tests/test_api_kyc.py — KYC Workflow API endpoint tests
IL-046 | banxe-emi-stack
"""

import pytest
from fastapi.testclient import TestClient

from api.deps import get_kyc_service
from api.main import app
from services.kyc.mock_kyc_workflow import MockKYCWorkflow

client = TestClient(app)

_KYC_PAYLOAD = {
    "customer_id": "cust-test-001",
    "kyc_type": "INDIVIDUAL",
    "entity_type": "INDIVIDUAL",
}


@pytest.fixture(autouse=True)
def fresh_kyc_service():
    svc = MockKYCWorkflow()
    app.dependency_overrides[get_kyc_service] = lambda: svc
    yield svc
    app.dependency_overrides.clear()


def test_create_workflow_returns_201():
    resp = client.post("/v1/kyc/workflows", json=_KYC_PAYLOAD)
    assert resp.status_code == 201


def test_create_workflow_has_id():
    resp = client.post("/v1/kyc/workflows", json=_KYC_PAYLOAD)
    assert "workflow_id" in resp.json()


def test_create_workflow_customer_id_matches():
    resp = client.post("/v1/kyc/workflows", json=_KYC_PAYLOAD)
    assert resp.json()["customer_id"] == "cust-test-001"


def test_create_workflow_initial_status():
    resp = client.post("/v1/kyc/workflows", json=_KYC_PAYLOAD)
    assert resp.json()["status"] in ("PENDING", "SUBMITTED", "INITIATED")


def test_create_workflow_kyc_type():
    resp = client.post("/v1/kyc/workflows", json=_KYC_PAYLOAD)
    assert resp.json()["kyc_type"] == "INDIVIDUAL"


def test_get_workflow_returns_200():
    wid = client.post("/v1/kyc/workflows", json=_KYC_PAYLOAD).json()["workflow_id"]
    resp = client.get(f"/v1/kyc/workflows/{wid}")
    assert resp.status_code == 200


def test_get_workflow_not_found_returns_404():
    resp = client.get("/v1/kyc/workflows/does-not-exist")
    assert resp.status_code == 404


def test_get_workflow_id_matches():
    wid = client.post("/v1/kyc/workflows", json=_KYC_PAYLOAD).json()["workflow_id"]
    resp = client.get(f"/v1/kyc/workflows/{wid}")
    assert resp.json()["workflow_id"] == wid


def test_submit_documents_returns_200():
    wid = client.post("/v1/kyc/workflows", json=_KYC_PAYLOAD).json()["workflow_id"]
    resp = client.post(
        f"/v1/kyc/workflows/{wid}/documents",
        json={"document_ids": ["doc-passport-001", "doc-proof-address-001"]},
    )
    assert resp.status_code == 200


def test_submit_documents_workflow_not_found():
    resp = client.post(
        "/v1/kyc/workflows/no-such-id/documents",
        json={"document_ids": ["doc-001"]},
    )
    assert resp.status_code == 404


def test_submit_documents_updates_status():
    wid = client.post("/v1/kyc/workflows", json=_KYC_PAYLOAD).json()["workflow_id"]
    resp = client.post(
        f"/v1/kyc/workflows/{wid}/documents",
        json={"document_ids": ["doc-passport-001"]},
    )
    assert resp.json()["status"] not in ("", None)


def test_reject_workflow_returns_200():
    wid = client.post("/v1/kyc/workflows", json=_KYC_PAYLOAD).json()["workflow_id"]
    resp = client.post(
        f"/v1/kyc/workflows/{wid}/reject",
        json={"reason": "INCOMPLETE_DOCUMENTS"},
    )
    assert resp.status_code == 200


def test_reject_workflow_status_rejected():
    wid = client.post("/v1/kyc/workflows", json=_KYC_PAYLOAD).json()["workflow_id"]
    client.post(
        f"/v1/kyc/workflows/{wid}/reject",
        json={"reason": "INCOMPLETE_DOCUMENTS"},
    )
    resp = client.get(f"/v1/kyc/workflows/{wid}")
    assert resp.json()["status"] == "REJECTED"


def test_reject_nonexistent_workflow_returns_404():
    resp = client.post(
        "/v1/kyc/workflows/bad-id/reject",
        json={"reason": "INCOMPLETE_DOCUMENTS"},
    )
    assert resp.status_code == 404


def test_reject_terminal_workflow_returns_422():
    wid = client.post("/v1/kyc/workflows", json=_KYC_PAYLOAD).json()["workflow_id"]
    # Reject once
    client.post(f"/v1/kyc/workflows/{wid}/reject", json={"reason": "INCOMPLETE_DOCUMENTS"})
    # Reject again → terminal
    resp = client.post(f"/v1/kyc/workflows/{wid}/reject", json={"reason": "INCOMPLETE_DOCUMENTS"})
    assert resp.status_code == 422


def test_kyb_workflow_type():
    payload = {**_KYC_PAYLOAD, "kyc_type": "BUSINESS", "entity_type": "CORPORATE"}
    resp = client.post("/v1/kyc/workflows", json=payload)
    assert resp.status_code == 201
    assert resp.json()["kyc_type"] == "BUSINESS"
