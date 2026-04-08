"""
tests/test_api_customers.py — Customer API endpoint tests
IL-046 | banxe-emi-stack
"""
import pytest
from fastapi.testclient import TestClient

from api.deps import get_customer_service
from api.main import app

client = TestClient(app)

_INDIVIDUAL_PAYLOAD = {
    "entity_type": "INDIVIDUAL",
    "email": "test@example.com",
    "individual": {
        "first_name": "Alice",
        "last_name": "Smith",
        "date_of_birth": "1990-01-15",
        "nationality": "GB",
        "address": {
            "line1": "1 High Street",
            "city": "London",
            "postcode": "EC1A 1BB",
            "country": "GB",
        },
    },
}


@pytest.fixture(autouse=True)
def reset_service():
    """Fresh service instance per test."""
    from services.customer.customer_service import InMemoryCustomerService
    svc = InMemoryCustomerService()
    app.dependency_overrides[get_customer_service] = lambda: svc
    yield
    app.dependency_overrides.clear()


def test_create_customer_returns_201():
    resp = client.post("/v1/customers", json=_INDIVIDUAL_PAYLOAD)
    assert resp.status_code == 201


def test_create_customer_returns_id():
    resp = client.post("/v1/customers", json=_INDIVIDUAL_PAYLOAD)
    data = resp.json()
    assert "customer_id" in data
    assert data["customer_id"]


def test_create_customer_entity_type():
    resp = client.post("/v1/customers", json=_INDIVIDUAL_PAYLOAD)
    assert resp.json()["entity_type"] == "INDIVIDUAL"


def test_create_customer_lifecycle_onboarding():
    resp = client.post("/v1/customers", json=_INDIVIDUAL_PAYLOAD)
    assert resp.json()["lifecycle_state"] == "ONBOARDING"


def test_create_customer_display_name():
    resp = client.post("/v1/customers", json=_INDIVIDUAL_PAYLOAD)
    assert resp.json()["display_name"] == "Alice Smith"


def test_create_customer_email_stored():
    resp = client.post("/v1/customers", json=_INDIVIDUAL_PAYLOAD)
    assert resp.json()["email"] == "test@example.com"


def test_create_customer_risk_level_low():
    resp = client.post("/v1/customers", json=_INDIVIDUAL_PAYLOAD)
    assert resp.json()["risk_level"] == "low"


def test_get_customer_returns_200():
    cid = client.post("/v1/customers", json=_INDIVIDUAL_PAYLOAD).json()["customer_id"]
    resp = client.get(f"/v1/customers/{cid}")
    assert resp.status_code == 200


def test_get_customer_not_found_returns_404():
    resp = client.get("/v1/customers/nonexistent-id")
    assert resp.status_code == 404


def test_list_customers_returns_200():
    resp = client.get("/v1/customers")
    assert resp.status_code == 200


def test_list_customers_empty_initially():
    resp = client.get("/v1/customers")
    data = resp.json()
    assert data["total"] == 0
    assert data["customers"] == []


def test_list_customers_after_create():
    client.post("/v1/customers", json=_INDIVIDUAL_PAYLOAD)
    resp = client.get("/v1/customers")
    assert resp.json()["total"] == 1


def test_list_customers_filter_by_state():
    client.post("/v1/customers", json=_INDIVIDUAL_PAYLOAD)
    resp = client.get("/v1/customers?state=ONBOARDING")
    assert resp.json()["total"] == 1


def test_list_customers_filter_wrong_state():
    client.post("/v1/customers", json=_INDIVIDUAL_PAYLOAD)
    resp = client.get("/v1/customers?state=ACTIVE")
    assert resp.json()["total"] == 0


def test_create_customer_missing_email_returns_422():
    payload = {k: v for k, v in _INDIVIDUAL_PAYLOAD.items() if k != "email"}
    resp = client.post("/v1/customers", json=payload)
    assert resp.status_code == 422


def test_get_customer_matches_created():
    cid = client.post("/v1/customers", json=_INDIVIDUAL_PAYLOAD).json()["customer_id"]
    resp = client.get(f"/v1/customers/{cid}")
    assert resp.json()["customer_id"] == cid


def test_create_second_customer_increments_list():
    client.post("/v1/customers", json=_INDIVIDUAL_PAYLOAD)
    payload2 = {**_INDIVIDUAL_PAYLOAD, "email": "bob@example.com"}
    if "individual" in payload2:
        payload2["individual"] = {**payload2["individual"], "first_name": "Bob"}
    client.post("/v1/customers", json=payload2)
    resp = client.get("/v1/customers")
    assert resp.json()["total"] == 2
