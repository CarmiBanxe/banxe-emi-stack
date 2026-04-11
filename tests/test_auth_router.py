"""
tests/test_auth_router.py — Auth API endpoint tests
IL-046 | banxe-emi-stack

Tests for POST /v1/auth/login.
"""

from __future__ import annotations

import jwt
import pytest
from fastapi.testclient import TestClient

from api.deps import get_customer_service
from api.main import app

client = TestClient(app)

# Use a deterministic secret so JWT assertions are stable
_TEST_SECRET = "test-secret-key"
_TEST_PIN = "654321"


_CUSTOMER_PAYLOAD = {
    "entity_type": "INDIVIDUAL",
    "email": "alice@example.com",
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
def setup_auth_env(monkeypatch):
    """Isolated service + deterministic env for every test.

    Module-level constants are loaded at import time so we must patch them
    directly (not via os.environ).
    """
    import api.routers.auth as auth_module

    monkeypatch.setattr(auth_module, "_SECRET_KEY", _TEST_SECRET)
    monkeypatch.setattr(auth_module, "_DEV_PIN", _TEST_PIN)

    from services.customer.customer_service import InMemoryCustomerService

    svc = InMemoryCustomerService()
    app.dependency_overrides[get_customer_service] = lambda: svc

    # Pre-register one customer via the HTTP API so metadata.email is set correctly
    client.post("/v1/customers", json=_CUSTOMER_PAYLOAD)

    yield

    app.dependency_overrides.clear()


# ── Happy path ─────────────────────────────────────────────────────────────────


def test_login_returns_200():
    resp = client.post("/v1/auth/login", json={"email": "alice@example.com", "pin": _TEST_PIN})
    assert resp.status_code == 200


def test_login_response_has_token():
    resp = client.post("/v1/auth/login", json={"email": "alice@example.com", "pin": _TEST_PIN})
    data = resp.json()
    assert "token" in data
    assert len(data["token"]) > 0


def test_login_response_has_expires_at():
    resp = client.post("/v1/auth/login", json={"email": "alice@example.com", "pin": _TEST_PIN})
    data = resp.json()
    assert "expires_at" in data


def test_login_token_is_valid_jwt():
    resp = client.post("/v1/auth/login", json={"email": "alice@example.com", "pin": _TEST_PIN})
    token = resp.json()["token"]
    payload = jwt.decode(token, _TEST_SECRET, algorithms=["HS256"])
    assert payload["email"] == "alice@example.com"
    assert "sub" in payload
    assert "exp" in payload


def test_login_token_subject_is_customer_id():
    resp = client.post("/v1/auth/login", json={"email": "alice@example.com", "pin": _TEST_PIN})
    token = resp.json()["token"]
    payload = jwt.decode(token, _TEST_SECRET, algorithms=["HS256"])
    # sub must be a non-empty string (the customer_id UUID)
    assert isinstance(payload["sub"], str)
    assert len(payload["sub"]) > 0


# ── Auth failures ──────────────────────────────────────────────────────────────


def test_login_wrong_pin_returns_401():
    resp = client.post("/v1/auth/login", json={"email": "alice@example.com", "pin": "000000"})
    assert resp.status_code == 401


def test_login_unknown_email_returns_401():
    resp = client.post("/v1/auth/login", json={"email": "nobody@example.com", "pin": _TEST_PIN})
    assert resp.status_code == 401


def test_login_unknown_email_does_not_reveal_existence():
    """Response body must be identical for wrong-email and wrong-pin (no enumeration)."""
    resp_no_email = client.post(
        "/v1/auth/login", json={"email": "nobody@example.com", "pin": _TEST_PIN}
    )
    resp_wrong_pin = client.post(
        "/v1/auth/login", json={"email": "alice@example.com", "pin": "000000"}
    )
    assert resp_no_email.json()["detail"] == resp_wrong_pin.json()["detail"]


# ── Validation (422) ───────────────────────────────────────────────────────────


def test_login_pin_too_short_returns_422():
    resp = client.post("/v1/auth/login", json={"email": "alice@example.com", "pin": "123"})
    assert resp.status_code == 422


def test_login_pin_non_numeric_returns_422():
    resp = client.post("/v1/auth/login", json={"email": "alice@example.com", "pin": "abc123"})
    assert resp.status_code == 422


def test_login_missing_email_returns_422():
    resp = client.post("/v1/auth/login", json={"pin": _TEST_PIN})
    assert resp.status_code == 422


def test_login_missing_pin_returns_422():
    resp = client.post("/v1/auth/login", json={"email": "alice@example.com"})
    assert resp.status_code == 422
