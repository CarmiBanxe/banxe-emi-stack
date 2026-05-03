"""
tests/test_auth_router.py — Auth API endpoint tests
IL-046 | banxe-emi-stack

Tests for POST /v1/auth/login.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
import jwt
import pytest

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
def setup_auth_env(monkeypatch, db_session):
    """Isolated service + deterministic secret/PIN + in-memory DB for every test.

    Sprint 3 refactor: secret is injected via TokenManager DI (AuthApplicationService),
    DEV_PIN is patched on the source-of-truth module (services.auth.auth_application_service).
    db_session (from conftest.py) provides a fresh SQLite :memory: database.
    """
    # Patch DEV_PIN where _validate_pin reads it (global lookup at call time)
    import services.auth.auth_application_service as auth_app_module

    monkeypatch.setattr(auth_app_module, "DEV_PIN", _TEST_PIN)

    # Override AuthApplicationService DI to inject deterministic JWT secret
    from services.auth.auth_application_service import (
        AuthApplicationService,
        get_auth_application_service,
    )
    from services.auth.token_manager import TokenManager

    test_auth_app = AuthApplicationService(
        token_manager=TokenManager(secret_key=_TEST_SECRET),
    )
    app.dependency_overrides[get_auth_application_service] = lambda: test_auth_app

    # InMemory customer service override
    from services.customer.customer_service import InMemoryCustomerService

    svc = InMemoryCustomerService()
    app.dependency_overrides[get_customer_service] = lambda: svc

    # Pre-register one customer via HTTP API (writes to InMemory + DB)
    client.post("/v1/customers", json=_CUSTOMER_PAYLOAD)

    yield

    app.dependency_overrides.pop(get_customer_service, None)
    app.dependency_overrides.pop(get_auth_application_service, None)


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
