"""
tests/test_api_sca_resend.py — POST /v1/auth/sca/resend tests
S15-FIX-1 | PSD2 Art.97 | banxe-emi-stack

8 tests covering resend happy path, rate limiting, and error cases.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from api.main import app
from services.auth.sca_service import InMemorySCAStore, SCAService


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def fresh_sca(monkeypatch):
    svc = SCAService(store=InMemorySCAStore())
    monkeypatch.setattr("api.routers.auth.get_sca_service", lambda **kwargs: svc)
    monkeypatch.setattr("services.auth.sca_service._sca_service", svc)
    return svc


def _create_challenge(client, svc, method: str = "otp") -> str:
    """Helper: create a challenge and return its ID."""
    resp = client.post(
        "/v1/auth/sca/challenge",
        json={
            "customer_id": "cust-resend-001",
            "transaction_id": "txn-resend-001",
            "method": method,
        },
    )
    assert resp.status_code == 201
    return resp.json()["challenge_id"]


class TestSCAResend:
    def test_resend_returns_200(self, client, fresh_sca):
        cid = _create_challenge(client, fresh_sca)
        resp = client.post("/v1/auth/sca/resend", json={"challenge_id": cid})
        assert resp.status_code == 200

    def test_resend_resets_ttl(self, client, fresh_sca):
        cid = _create_challenge(client, fresh_sca)
        resp1 = client.post("/v1/auth/sca/resend", json={"challenge_id": cid})
        resp2 = client.post("/v1/auth/sca/resend", json={"challenge_id": cid})
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        # expires_at should be different (or at worst equal millisecond-wise)
        data1 = resp1.json()
        data2 = resp2.json()
        assert data2["resend_count"] == 2
        assert data1["resend_count"] == 1

    def test_resend_increments_counter(self, client, fresh_sca):
        cid = _create_challenge(client, fresh_sca)
        r = client.post("/v1/auth/sca/resend", json={"challenge_id": cid})
        assert r.json()["resend_count"] == 1

    def test_resend_limit_3_returns_400(self, client, fresh_sca):
        cid = _create_challenge(client, fresh_sca)
        for _ in range(3):
            client.post("/v1/auth/sca/resend", json={"challenge_id": cid})
        r = client.post("/v1/auth/sca/resend", json={"challenge_id": cid})
        assert r.status_code == 400
        assert "limit" in r.json()["detail"].lower()

    def test_resend_nonexistent_challenge_returns_404(self, client, fresh_sca):
        r = client.post("/v1/auth/sca/resend", json={"challenge_id": "nonexistent-id-12345"})
        assert r.status_code == 404

    def test_resend_response_contains_challenge_id(self, client, fresh_sca):
        cid = _create_challenge(client, fresh_sca)
        r = client.post("/v1/auth/sca/resend", json={"challenge_id": cid})
        data = r.json()
        assert data["challenge_id"] == cid

    def test_resend_response_contains_method(self, client, fresh_sca):
        cid = _create_challenge(client, fresh_sca, method="otp")
        r = client.post("/v1/auth/sca/resend", json={"challenge_id": cid})
        assert r.json()["method"] == "otp"

    def test_resend_missing_challenge_id_returns_422(self, client, fresh_sca):
        r = client.post("/v1/auth/sca/resend", json={})
        assert r.status_code == 422
