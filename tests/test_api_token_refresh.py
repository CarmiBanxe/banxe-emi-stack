"""
tests/test_api_token_refresh.py — Token refresh endpoint tests
S15-05 | PSD2 RTS Art.4 | banxe-emi-stack

Tests for POST /v1/auth/token/refresh.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import uuid

from fastapi.testclient import TestClient
import jwt
import pytest

from api.main import app
from services.auth.token_manager import _ALGORITHM, _REFRESH_TTL_DAYS, _TTL_HOURS

client = TestClient(app)

# Deterministic secret used by both test JWT signing and server-side TokenManager
_TEST_SECRET = "test-secret-key"


@pytest.fixture(autouse=True)
def setup_refresh_env():
    """Inject deterministic JWT secret via DI override for /auth/token/refresh.

    Sprint 3: secret is no longer a module-level constant in api.routers.auth.
    We override AuthApplicationService DI so server-side TokenManager uses _TEST_SECRET,
    matching the secret used by _make_refresh_token() in this file.
    """
    from services.auth.auth_application_service import (
        AuthApplicationService,
        get_auth_application_service,
    )
    from services.auth.token_manager import TokenManager

    test_auth_app = AuthApplicationService(
        token_manager=TokenManager(secret_key=_TEST_SECRET),
    )
    app.dependency_overrides[get_auth_application_service] = lambda: test_auth_app

    yield

    app.dependency_overrides.pop(get_auth_application_service, None)


def _make_refresh_token(customer_id: str = "cust-001", days_offset: int = 0) -> str:
    """Create a valid refresh token for tests (includes jti for replay prevention)."""
    now = datetime.now(tz=UTC)
    payload = {
        "sub": customer_id,
        "type": "refresh",
        "jti": str(uuid.uuid4()),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=_REFRESH_TTL_DAYS + days_offset)).timestamp()),
    }
    return jwt.encode(payload, _TEST_SECRET, algorithm=_ALGORITHM)


def _make_access_token_as_refresh(customer_id: str = "cust-001") -> str:
    """Create an access token (type != 'refresh') — should be rejected."""
    now = datetime.now(tz=UTC)
    payload = {
        "sub": customer_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=_TTL_HOURS)).timestamp()),
        # No "type": "refresh"
    }
    return jwt.encode(payload, _TEST_SECRET, algorithm=_ALGORITHM)


class TestTokenRefresh:
    def test_valid_refresh_token_returns_200(self):
        refresh_token = _make_refresh_token()
        resp = client.post("/v1/auth/token/refresh", json={"refresh_token": refresh_token})
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert "refresh_token" in data
        assert "expires_at" in data
        assert data["token_type"] == "bearer"

    def test_new_tokens_are_valid_jwts(self):
        """Returned tokens should decode with the server secret."""
        refresh_token = _make_refresh_token("cust-002")
        resp = client.post("/v1/auth/token/refresh", json={"refresh_token": refresh_token})
        assert resp.status_code == 200
        data = resp.json()

        # Access token
        payload = jwt.decode(data["token"], _TEST_SECRET, algorithms=[_ALGORITHM])
        assert payload["sub"] == "cust-002"

        # New refresh token
        refresh_payload = jwt.decode(data["refresh_token"], _TEST_SECRET, algorithms=[_ALGORITHM])
        assert refresh_payload["sub"] == "cust-002"
        assert refresh_payload["type"] == "refresh"

    def test_refresh_token_rotated(self):
        """New refresh token should differ from the original (rotation)."""
        refresh_token = _make_refresh_token()
        resp = client.post("/v1/auth/token/refresh", json={"refresh_token": refresh_token})
        assert resp.json()["refresh_token"] != refresh_token

    def test_expired_refresh_token_returns_401(self):
        """Expired refresh token must be rejected."""
        now = datetime.now(tz=UTC)
        payload = {
            "sub": "cust-001",
            "type": "refresh",
            "jti": str(uuid.uuid4()),
            "iat": int((now - timedelta(days=10)).timestamp()),
            "exp": int((now - timedelta(days=3)).timestamp()),  # expired 3 days ago
        }
        expired_token = jwt.encode(payload, _TEST_SECRET, algorithm=_ALGORITHM)
        resp = client.post("/v1/auth/token/refresh", json={"refresh_token": expired_token})
        assert resp.status_code == 401
        assert "expired" in resp.json()["detail"].lower()

    def test_invalid_signature_returns_401(self):
        """Token signed with wrong key must be rejected."""
        payload = {
            "sub": "cust-001",
            "type": "refresh",
            "jti": str(uuid.uuid4()),
            "iat": int(datetime.now(tz=UTC).timestamp()),
            "exp": int((datetime.now(tz=UTC) + timedelta(days=7)).timestamp()),
        }
        bad_token = jwt.encode(payload, "wrong-secret-key", algorithm=_ALGORITHM)
        resp = client.post("/v1/auth/token/refresh", json={"refresh_token": bad_token})
        assert resp.status_code == 401

    def test_access_token_used_as_refresh_returns_401(self):
        """Access tokens (type != 'refresh') must be rejected."""
        access_token = _make_access_token_as_refresh()
        resp = client.post("/v1/auth/token/refresh", json={"refresh_token": access_token})
        assert resp.status_code == 401
        # Server says "Token is not a refresh token" — check semantic meaning, not exact word
        detail = resp.json()["detail"].lower()
        assert "refresh" in detail and "not" in detail

    def test_empty_refresh_token_returns_422(self):
        """Empty refresh_token field must fail validation."""
        resp = client.post("/v1/auth/token/refresh", json={"refresh_token": ""})
        assert resp.status_code in (401, 422)

    def test_garbage_token_returns_401(self):
        """Non-JWT string must be rejected."""
        resp = client.post("/v1/auth/token/refresh", json={"refresh_token": "not-a-jwt"})
        assert resp.status_code == 401
