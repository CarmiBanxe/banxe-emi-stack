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
    """Isolated service + deterministic env + in-memory DB for every test.

    Module-level constants are loaded at import time so we must patch them
    directly (not via os.environ). db_session (from conftest.py) injects a
    fresh SQLite :memory: database and overrides the app's get_db dependency.
    """
    import api.routers.auth as auth_module

    monkeypatch.setattr(auth_module, "_SECRET_KEY", _TEST_SECRET)
    monkeypatch.setattr(auth_module, "_DEV_PIN", _TEST_PIN)

    from services.customer.customer_service import InMemoryCustomerService

    svc = InMemoryCustomerService()
    app.dependency_overrides[get_customer_service] = lambda: svc

    # Pre-register one customer via the HTTP API — writes to both InMemory and DB
    client.post("/v1/customers", json=_CUSTOMER_PAYLOAD)

    yield

    # db_session fixture cleans up get_db override; remove customer_service override
    app.dependency_overrides.pop(get_customer_service, None)


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


# ── S13-06: Direct unit tests for auth helpers (coverage lines 54, 66, 104-152) ─


def _make_in_memory_customer(svc, email: str):
    """Create a customer profile with email stored in metadata (matches auth lookup)."""
    from datetime import date

    from services.customer.customer_port import (
        Address,
        CreateCustomerRequest,
        EntityType,
        IndividualProfile,
    )

    address = Address(line1="1 Test St", city="London", country="GB", postcode="EC1A 1BB")
    individual = IndividualProfile(
        first_name="Test",
        last_name="User",
        date_of_birth=date(1990, 1, 1),
        nationality="GB",
        address=address,
    )
    req = CreateCustomerRequest(entity_type=EntityType.INDIVIDUAL, individual=individual)
    profile = svc.create_customer(req)
    profile.metadata["email"] = email
    return profile


class TestGetCustomerByEmailMemory:
    """Direct tests for _get_customer_by_email_memory (line 66)."""

    def test_found_returns_customer_id_and_email(self):
        from api.routers.auth import _get_customer_by_email_memory
        from services.customer.customer_service import InMemoryCustomerService

        svc = InMemoryCustomerService()
        _make_in_memory_customer(svc, "bob@example.com")
        result = _get_customer_by_email_memory(svc, "bob@example.com")
        assert result is not None
        cid, email = result
        assert email == "bob@example.com"
        assert len(cid) > 0

    def test_not_found_returns_none(self):
        from api.routers.auth import _get_customer_by_email_memory
        from services.customer.customer_service import InMemoryCustomerService

        svc = InMemoryCustomerService()
        result = _get_customer_by_email_memory(svc, "nobody@example.com")
        assert result is None

    def test_multiple_customers_finds_correct(self):
        from api.routers.auth import _get_customer_by_email_memory
        from services.customer.customer_service import InMemoryCustomerService

        svc = InMemoryCustomerService()
        _make_in_memory_customer(svc, "alice@x.com")
        _make_in_memory_customer(svc, "bob@x.com")
        result = _get_customer_by_email_memory(svc, "bob@x.com")
        assert result is not None
        _, email = result
        assert email == "bob@x.com"


@pytest.mark.asyncio
class TestGetCustomerByEmailDb:
    """Direct async tests for _get_customer_by_email_db (line 54)."""

    async def test_found_returns_customer(self):
        from unittest.mock import AsyncMock, MagicMock

        from api.routers.auth import _get_customer_by_email_db

        mock_customer = MagicMock()
        mock_customer.customer_id = "cust-db-001"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_customer
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        result = await _get_customer_by_email_db(db, "alice@db.com")
        assert result is mock_customer

    async def test_not_found_returns_none(self):
        from unittest.mock import AsyncMock, MagicMock

        from api.routers.auth import _get_customer_by_email_db

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        result = await _get_customer_by_email_db(db, "ghost@db.com")
        assert result is None


@pytest.mark.asyncio
class TestLoginHandlerDirect:
    """
    Direct async tests for login() handler function.
    These cover lines 104-152 by calling the handler without HTTP.
    """

    def _make_request(self, email: str, pin: str):
        from unittest.mock import MagicMock

        from api.models.auth import LoginRequest

        req = MagicMock()  # fastapi Request mock
        req.headers.get = MagicMock(return_value=None)
        return LoginRequest(email=email, pin=pin), req

    async def test_login_db_customer_found(self):
        from unittest.mock import AsyncMock, MagicMock, patch

        import api.routers.auth as auth_module
        from api.routers.auth import login

        body, request = self._make_request("db@test.com", "123456")

        mock_customer = MagicMock()
        mock_customer.customer_id = "cust-db-xyz"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_customer
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)
        db.add = MagicMock()
        db.flush = AsyncMock()

        from services.customer.customer_service import InMemoryCustomerService

        svc = InMemoryCustomerService()

        with (
            patch.object(auth_module, "_DEV_PIN", "123456"),
            patch.object(auth_module, "_SECRET_KEY", "test-secret"),
        ):
            result = await login(body=body, request=request, db=db, svc=svc)

        assert result.token
        assert result.expires_at

    async def test_login_db_exception_falls_to_memory(self):
        from unittest.mock import AsyncMock, patch

        import api.routers.auth as auth_module
        from api.routers.auth import login
        from services.customer.customer_service import InMemoryCustomerService

        body, request = self._make_request("mem@test.com", "654321")

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=Exception("DB connection refused"))

        svc = InMemoryCustomerService()
        _make_in_memory_customer(svc, "mem@test.com")

        with (
            patch.object(auth_module, "_DEV_PIN", "654321"),
            patch.object(auth_module, "_SECRET_KEY", "test-secret"),
        ):
            result = await login(body=body, request=request, db=db, svc=svc)

        assert result.token

    async def test_login_customer_not_found_raises_401(self):
        from unittest.mock import AsyncMock, MagicMock

        from fastapi import HTTPException

        from api.routers.auth import login
        from services.customer.customer_service import InMemoryCustomerService

        body, request = self._make_request("ghost@test.com", "123456")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)
        svc = InMemoryCustomerService()  # empty — no customer

        with pytest.raises(HTTPException) as exc_info:
            await login(body=body, request=request, db=db, svc=svc)
        assert exc_info.value.status_code == 401

    async def test_login_wrong_pin_raises_401(self):
        from unittest.mock import AsyncMock, MagicMock, patch

        from fastapi import HTTPException

        import api.routers.auth as auth_module
        from api.routers.auth import login
        from services.customer.customer_service import InMemoryCustomerService

        body, request = self._make_request("db@test.com", "000000")

        mock_customer = MagicMock()
        mock_customer.customer_id = "cust-001"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_customer
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)
        svc = InMemoryCustomerService()

        with (
            patch.object(auth_module, "_DEV_PIN", "123456"),
            pytest.raises(HTTPException) as exc_info,
        ):
            await login(body=body, request=request, db=db, svc=svc)
        assert exc_info.value.status_code == 401

    async def test_login_session_persist_failure_still_returns_token(self):
        """Session persist failure (lines 138-149) must not abort login."""
        from unittest.mock import AsyncMock, MagicMock, patch

        import api.routers.auth as auth_module
        from api.routers.auth import login
        from services.customer.customer_service import InMemoryCustomerService

        body, request = self._make_request("db@test.com", "123456")

        mock_customer = MagicMock()
        mock_customer.customer_id = "cust-001"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_customer
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)
        db.add = MagicMock(side_effect=Exception("DB is full"))
        svc = InMemoryCustomerService()

        with (
            patch.object(auth_module, "_DEV_PIN", "123456"),
            patch.object(auth_module, "_SECRET_KEY", "test-secret"),
        ):
            result = await login(body=body, request=request, db=db, svc=svc)

        assert result.token  # login still succeeds despite session persist failure
