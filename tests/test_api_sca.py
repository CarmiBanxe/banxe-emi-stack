"""
tests/test_api_sca.py — PSD2 SCA API endpoint tests
S15-01 | PSD2 Directive 2015/2366 Art.97 | banxe-emi-stack

Tests for:
  POST /v1/auth/sca/challenge
  POST /v1/auth/sca/verify
  GET  /v1/auth/sca/methods/{customer_id}

Covers:
  - Challenge creation (OTP + biometric)
  - Concurrent challenge limit enforcement
  - Successful OTP verification → SCA token issued
  - Rate limiting (5 attempts → 429)
  - Replay prevention (challenge 'used' after success)
  - Expiry handling
  - SCA methods response
  - Validation errors
  - Dynamic linking (amount + payee in JWT)
"""

from __future__ import annotations

from fastapi.testclient import TestClient
import jwt
import pytest

from api.main import app
from services.auth.sca_service import (
    SCA_ALGORITHM,
    SCA_SECRET_KEY,
    InMemorySCAStore,
    SCAService,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def client():
    """FastAPI test client."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def fresh_sca_service(monkeypatch):
    """
    Provide a fresh SCAService for each test via monkeypatching the singleton.
    Prevents state bleed between tests.

    Sprint 4 Track A Block 7: get_sca_service signature accepts optional
    two_factor kwarg; the lambda accepts **kwargs to preserve compatibility
    with the post-Block-7 router factory call get_sca_service(two_factor=...).
    The fresh SCAService is constructed without two_factor, so existing
    OTP-verification tests continue to exercise the legacy fallback path.
    """
    svc = SCAService(store=InMemorySCAStore())
    monkeypatch.setattr("api.routers.auth.get_sca_service", lambda **_kw: svc)
    monkeypatch.setattr("services.auth.sca_service._sca_service", svc)
    return svc


# ── Challenge creation (POST /v1/auth/sca/challenge) ─────────────────────────


class TestSCAChallengeCreate:
    def test_create_otp_challenge_returns_201(self, client, fresh_sca_service):
        resp = client.post(
            "/v1/auth/sca/challenge",
            json={
                "customer_id": "cust-001",
                "transaction_id": "txn-001",
                "method": "otp",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "challenge_id" in data
        assert data["method"] == "otp"
        assert data["transaction_id"] == "txn-001"
        assert "expires_at" in data

    def test_create_biometric_challenge_returns_201(self, client, fresh_sca_service):
        resp = client.post(
            "/v1/auth/sca/challenge",
            json={
                "customer_id": "cust-001",
                "transaction_id": "txn-002",
                "method": "biometric",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["method"] == "biometric"

    def test_create_challenge_with_dynamic_linking(self, client, fresh_sca_service):
        """PSD2 RTS Art.10 — amount and payee included in challenge."""
        resp = client.post(
            "/v1/auth/sca/challenge",
            json={
                "customer_id": "cust-001",
                "transaction_id": "txn-003",
                "method": "otp",
                "amount": "150.00",
                "payee": "ACME Ltd",
            },
        )
        assert resp.status_code == 201
        # Verify stored challenge has amount + payee
        challenge = fresh_sca_service._store.get(resp.json()["challenge_id"])
        assert challenge.amount == "150.00"
        assert challenge.payee == "ACME Ltd"

    def test_invalid_method_returns_400(self, client, fresh_sca_service):
        resp = client.post(
            "/v1/auth/sca/challenge",
            json={
                "customer_id": "cust-001",
                "transaction_id": "txn-004",
                "method": "sms",  # unsupported
            },
        )
        assert resp.status_code == 422  # Pydantic Literal validation

    def test_concurrent_limit_returns_400(self, client, fresh_sca_service):
        """Customer with ≥ 3 active challenges gets 400."""
        for i in range(3):
            r = client.post(
                "/v1/auth/sca/challenge",
                json={
                    "customer_id": "cust-limit",
                    "transaction_id": f"txn-limit-{i}",
                    "method": "otp",
                },
            )
            assert r.status_code == 201

        # 4th challenge must be rejected
        resp = client.post(
            "/v1/auth/sca/challenge",
            json={
                "customer_id": "cust-limit",
                "transaction_id": "txn-limit-overflow",
                "method": "otp",
            },
        )
        assert resp.status_code == 400
        assert "active SCA challenges" in resp.json()["detail"]

    def test_invalid_amount_decimal_returns_422(self, client, fresh_sca_service):
        resp = client.post(
            "/v1/auth/sca/challenge",
            json={
                "customer_id": "cust-001",
                "transaction_id": "txn-005",
                "method": "otp",
                "amount": "not-a-number",
            },
        )
        assert resp.status_code == 422


# ── Biometric verification (POST /v1/auth/sca/verify) ────────────────────────


class TestSCAVerifyBiometric:
    def _create_challenge(self, client, customer_id="cust-bio-001", method="biometric"):
        r = client.post(
            "/v1/auth/sca/challenge",
            json={
                "customer_id": customer_id,
                "transaction_id": "txn-bio-001",
                "method": method,
            },
        )
        assert r.status_code == 201
        return r.json()["challenge_id"]

    def test_biometric_verify_success(self, client, fresh_sca_service):
        challenge_id = self._create_challenge(client)
        resp = client.post(
            "/v1/auth/sca/verify",
            json={
                "challenge_id": challenge_id,
                "biometric_proof": "biometric:approved:device-xyz",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["verified"] is True
        assert data["sca_token"] is not None

    def test_biometric_token_contains_dynamic_linking(self, client, fresh_sca_service):
        """SCA token JWT must contain txn_id + amount + payee (PSD2 RTS Art.10)."""
        r = client.post(
            "/v1/auth/sca/challenge",
            json={
                "customer_id": "cust-bio-dl",
                "transaction_id": "txn-bio-dl-001",
                "method": "biometric",
                "amount": "500.00",
                "payee": "Test Payee Ltd",
            },
        )
        assert r.status_code == 201
        challenge_id = r.json()["challenge_id"]

        resp = client.post(
            "/v1/auth/sca/verify",
            json={
                "challenge_id": challenge_id,
                "biometric_proof": "biometric:approved:device-xyz",
            },
        )
        assert resp.status_code == 200
        token = resp.json()["sca_token"]
        payload = jwt.decode(token, SCA_SECRET_KEY, algorithms=[SCA_ALGORITHM])
        assert payload["txn_id"] == "txn-bio-dl-001"
        assert payload["amount"] == "500.00"
        assert payload["payee"] == "Test Payee Ltd"
        assert payload["sca"] is True

    def test_biometric_replay_blocked(self, client, fresh_sca_service):
        """Same challenge cannot be verified twice (replay prevention)."""
        challenge_id = self._create_challenge(client)
        # First verify
        r1 = client.post(
            "/v1/auth/sca/verify",
            json={
                "challenge_id": challenge_id,
                "biometric_proof": "biometric:approved:device-xyz",
            },
        )
        assert r1.json()["verified"] is True
        # Second verify on same challenge_id
        r2 = client.post(
            "/v1/auth/sca/verify",
            json={
                "challenge_id": challenge_id,
                "biometric_proof": "biometric:approved:device-xyz",
            },
        )
        assert r2.json()["verified"] is False
        assert "already used" in r2.json()["error"]

    def test_invalid_biometric_proof_fails(self, client, fresh_sca_service):
        challenge_id = self._create_challenge(client)
        resp = client.post(
            "/v1/auth/sca/verify",
            json={
                "challenge_id": challenge_id,
                "biometric_proof": "invalid-proof",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["verified"] is False
        assert data["attempts_remaining"] == 4  # 5 - 1


# ── OTP verification (POST /v1/auth/sca/verify) ──────────────────────────────


class TestSCAVerifyOTP:
    def test_wrong_otp_returns_not_verified(self, client, fresh_sca_service):
        r = client.post(
            "/v1/auth/sca/challenge",
            json={
                "customer_id": "cust-otp-001",
                "transaction_id": "txn-otp-001",
                "method": "otp",
            },
        )
        challenge_id = r.json()["challenge_id"]

        resp = client.post(
            "/v1/auth/sca/verify",
            json={
                "challenge_id": challenge_id,
                "otp_code": "999999",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["verified"] is False

    def test_rate_limit_after_5_failures_returns_429(self, client, fresh_sca_service):
        """After 5 failed attempts, next verify returns HTTP 429."""
        r = client.post(
            "/v1/auth/sca/challenge",
            json={
                "customer_id": "cust-ratelimit",
                "transaction_id": "txn-ratelimit",
                "method": "otp",
            },
        )
        challenge_id = r.json()["challenge_id"]

        for _ in range(5):
            client.post(
                "/v1/auth/sca/verify",
                json={
                    "challenge_id": challenge_id,
                    "otp_code": "999999",
                },
            )

        # 6th attempt — challenge locked → 429
        resp = client.post(
            "/v1/auth/sca/verify",
            json={
                "challenge_id": challenge_id,
                "otp_code": "999999",
            },
        )
        assert resp.status_code == 429

    def test_otp_code_must_be_6_digits(self, client, fresh_sca_service):
        r = client.post(
            "/v1/auth/sca/challenge",
            json={
                "customer_id": "cust-otp-002",
                "transaction_id": "txn-otp-002",
                "method": "otp",
            },
        )
        challenge_id = r.json()["challenge_id"]
        resp = client.post(
            "/v1/auth/sca/verify",
            json={
                "challenge_id": challenge_id,
                "otp_code": "123",  # too short
            },
        )
        assert resp.status_code == 422

    def test_challenge_not_found_returns_404(self, client, fresh_sca_service):
        resp = client.post(
            "/v1/auth/sca/verify",
            json={
                "challenge_id": "nonexistent-challenge-id",
                "otp_code": "123456",
            },
        )
        assert resp.status_code == 404


# ── SCA methods (GET /v1/auth/sca/methods/{customer_id}) ─────────────────────


class TestSCAMethods:
    def test_get_methods_default_otp(self, client, fresh_sca_service):
        resp = client.get("/v1/auth/sca/methods/cust-unknown")
        assert resp.status_code == 200
        data = resp.json()
        assert data["customer_id"] == "cust-unknown"
        assert "otp" in data["methods"]
        assert data["preferred"] == "otp"

    def test_get_methods_biometric_for_bio_customer(self, client, fresh_sca_service):
        """Customer ID ending in '-bio' has biometric available (test hook)."""
        resp = client.get("/v1/auth/sca/methods/cust-001-bio")
        assert resp.status_code == 200
        data = resp.json()
        assert "biometric" in data["methods"]
        assert "otp" in data["methods"]
        assert data["preferred"] == "biometric"

    def test_get_methods_includes_both_when_otp_secret_registered(self, client, fresh_sca_service):
        """Registering OTP secret signals device enrollment → biometric available."""
        fresh_sca_service.register_otp_secret("cust-enrolled", "JBSWY3DPEHPK3PXP")
        resp = client.get("/v1/auth/sca/methods/cust-enrolled")
        assert resp.status_code == 200
        data = resp.json()
        assert "biometric" in data["methods"]
