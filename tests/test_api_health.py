"""
tests/test_api_health.py — API health endpoint tests
IL-046 | banxe-emi-stack
"""

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_liveness_returns_200():
    resp = client.get("/health")
    assert resp.status_code == 200


def test_liveness_status_ok():
    resp = client.get("/health")
    assert resp.json()["status"] == "ok"


def test_liveness_version_present():
    resp = client.get("/health")
    assert "version" in resp.json()


def test_liveness_plane_product():
    resp = client.get("/health")
    assert resp.json()["plane"] == "Product"


def test_readiness_returns_200():
    resp = client.get("/health/ready")
    assert resp.status_code == 200


def test_readiness_has_checks():
    resp = client.get("/health/ready")
    data = resp.json()
    assert "checks" in data
    assert "kyc" in data["checks"]
    assert "payment" in data["checks"]


def test_readiness_status_field():
    resp = client.get("/health/ready")
    assert resp.json()["status"] in ("ok", "degraded")


def test_request_id_injected_in_response():
    resp = client.get("/health")
    assert "x-request-id" in resp.headers


def test_request_id_echoed_when_provided():
    resp = client.get("/health", headers={"X-Request-ID": "test-123"})
    assert resp.headers["x-request-id"] == "test-123"


def test_unknown_route_returns_404():
    resp = client.get("/not-a-real-endpoint")
    assert resp.status_code == 404


def test_openapi_schema_reachable():
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    assert "paths" in resp.json()


def test_docs_reachable():
    resp = client.get("/docs")
    assert resp.status_code == 200


def test_readiness_kyc_check_ok():
    resp = client.get("/health/ready")
    assert resp.json()["checks"]["kyc"] in ("ok", "degraded")


def test_readiness_payment_check_ok():
    resp = client.get("/health/ready")
    assert resp.json()["checks"]["payment"] in ("ok", "degraded")


def test_liveness_content_type_json():
    resp = client.get("/health")
    assert "application/json" in resp.headers["content-type"]
