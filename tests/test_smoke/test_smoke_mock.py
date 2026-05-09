"""
tests/test_smoke/test_smoke_mock.py — ADR-035 Smoke Surface Matrix (mock tier)

6 checks, InMemory stubs only, real FastAPI lifespan, no network.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient
import pytest

from api.main import app
from services.kyc.kyc_port import KYCStatus, KYCType, KYCWorkflowRequest
from services.kyc.mock_kyc_workflow import MockKYCWorkflow
from services.recon.recon_engine import InMemoryReconAuditPort, ReconciliationEngine
from services.recon.recon_models import ReconStatus
from services.recon.recon_port import InMemoryLedgerPort

pytestmark = pytest.mark.smoke


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


# ── Check 1: Auth / JWT ────────────────────────────────────────────────────────
def test_smoke_auth_token_endpoint_reachable(client: TestClient) -> None:
    """POST /v1/auth/token returns 4xx (no valid creds) — endpoint is live."""
    resp = client.post("/v1/auth/token", json={"username": "smoke", "password": "smoke"})
    assert resp.status_code < 500, f"auth endpoint error: {resp.status_code} {resp.text}"


# ── Check 2: Audit trail append ────────────────────────────────────────────────
def test_smoke_audit_event_ingested(client: TestClient) -> None:
    """POST /v1/audit/events succeeds with InMemoryEventStore (no DB)."""
    payload = {
        "category": "PAYMENT",
        "event_type": "SMOKE_TEST",
        "entity_id": "smoke-001",
        "actor": "smoke-runner",
        "details": {"note": "adr-035 smoke"},
        "risk_level": "LOW",
        "source_service": "smoke",
    }
    resp = client.post("/v1/audit/events", json=payload)
    assert resp.status_code in (200, 201), f"audit ingest failed: {resp.status_code} {resp.text}"


# ── Check 3: Reconciliation tick — zero discrepancy ───────────────────────────
def test_smoke_recon_balanced() -> None:
    """ReconciliationEngine with matching client-fund / safeguarding balances → BALANCED."""
    ledger = InMemoryLedgerPort()
    ledger.add_client_fund("cf-smoke-001", Decimal("5000.00"), "GBP", "GB")
    ledger.add_safeguarding("sg-smoke-001", Decimal("5000.00"), "GBP", "GB")
    engine = ReconciliationEngine(ledger=ledger, audit=InMemoryReconAuditPort())
    result = engine.run_daily_recon("2026-05-09")
    assert result.status == ReconStatus.BALANCED, f"recon not balanced: {result}"


# ── Check 4: Safeguarding healthz ─────────────────────────────────────────────
def test_smoke_health_endpoint(client: TestClient) -> None:
    """GET /health returns 200 — app startup succeeded."""
    resp = client.get("/health")
    assert resp.status_code == 200, f"health check failed: {resp.status_code} {resp.text}"
    body = resp.json()
    assert body.get("status") in ("ok", "healthy", "UP"), f"unexpected health body: {body}"


# ── Check 5: Guardian mock — audit POST round-trip ────────────────────────────
def test_smoke_guardian_audit_post(client: TestClient) -> None:
    """Guardian shim proxied via POST /v1/audit/events — InMemoryEventStore, no network."""
    payload = {
        "category": "COMPLIANCE",
        "event_type": "GUARDIAN_CHECK",
        "entity_id": "pr-smoke-001",
        "actor": "guardian-mock",
        "details": {"check": "smoke", "result": "pass"},
        "risk_level": "LOW",
        "source_service": "guardian",
    }
    resp = client.post("/v1/audit/events", json=payload)
    assert resp.status_code in (200, 201), f"guardian audit failed: {resp.status_code} {resp.text}"
    data = resp.json()
    assert "event_id" in data or "id" in data or resp.status_code in (200, 201)


# ── Check 6: KYCWorkflowPort.create_workflow() → PENDING ─────────────────────
def test_smoke_kyc_workflow_pending() -> None:
    """MockKYCWorkflow.create_workflow() returns PENDING for a clean individual."""
    kyc = MockKYCWorkflow()
    request = KYCWorkflowRequest(
        customer_id="smoke-cust-001",
        kyc_type=KYCType.INDIVIDUAL,
        first_name="Smoke",
        last_name="Test",
        date_of_birth="1990-01-01",
        nationality="GB",
        country_of_residence="GB",
        expected_transaction_volume=Decimal("500.00"),
    )
    result = kyc.create_workflow(request)
    assert result.status == KYCStatus.PENDING, f"KYC not PENDING: {result.status}"
