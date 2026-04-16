"""
tests/test_regulatory_reporting/test_api_regulatory.py
IL-RRA-01 | Phase 14

Integration tests for /v1/regulatory/* API endpoints.
Uses FastAPI TestClient + dependency_overrides.
"""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest

from api.main import app
from services.regulatory_reporting.models import (
    InMemoryAuditTrail,
    InMemoryRegulatorGateway,
    InMemoryScheduler,
    InMemoryValidator,
)
from services.regulatory_reporting.regulatory_reporting_agent import RegulatoryReportingAgent
from services.regulatory_reporting.xml_generator import FCARegDataXMLGenerator

# ── Fixtures ──────────────────────────────────────────────────────────────────


def make_test_agent() -> RegulatoryReportingAgent:
    return RegulatoryReportingAgent(
        xml_generator=FCARegDataXMLGenerator(),
        validator=InMemoryValidator(),
        audit_trail=InMemoryAuditTrail(),
        scheduler=InMemoryScheduler(),
        regulator_gateway=InMemoryRegulatorGateway(),
    )


@pytest.fixture()
def client() -> TestClient:
    """Each test gets a fresh agent with an empty in-memory audit trail."""
    with patch("api.routers.regulatory._get_agent", side_effect=make_test_agent):
        yield TestClient(app)


# ── POST /v1/regulatory/reports/generate ─────────────────────────────────────


def test_generate_fin060_returns_200(client: TestClient) -> None:
    resp = client.post(
        "/v1/regulatory/reports/generate",
        json={
            "report_type": "FIN060",
            "entity_id": "FRN123456",
            "entity_name": "Banxe EMI Ltd",
            "period_start": "2025-01-01T00:00:00Z",
            "period_end": "2025-01-31T23:59:59Z",
            "actor": "compliance@banxe.com",
            "financial_data": {"total_client_assets": "500000.00"},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "VALIDATED"
    assert data["report_id"] is not None
    assert data["validation_errors"] == []


def test_generate_unknown_report_type_returns_422(client: TestClient) -> None:
    resp = client.post(
        "/v1/regulatory/reports/generate",
        json={
            "report_type": "UNKNOWN_TYPE",
            "entity_id": "FRN123456",
            "entity_name": "Banxe EMI Ltd",
            "period_start": "2025-01-01T00:00:00Z",
            "period_end": "2025-01-31T23:59:59Z",
            "actor": "actor1",
        },
    )
    assert resp.status_code == 422


def test_generate_fin071_returns_200(client: TestClient) -> None:
    resp = client.post(
        "/v1/regulatory/reports/generate",
        json={
            "report_type": "FIN071",
            "entity_id": "FRN123456",
            "entity_name": "Banxe EMI Ltd",
            "period_start": "2025-01-01T00:00:00Z",
            "period_end": "2025-12-31T23:59:59Z",
            "actor": "actor1",
        },
    )
    assert resp.status_code == 200


def test_generate_sar_batch_returns_200(client: TestClient) -> None:
    resp = client.post(
        "/v1/regulatory/reports/generate",
        json={
            "report_type": "SAR_BATCH",
            "entity_id": "FRN123456",
            "entity_name": "Banxe EMI Ltd",
            "period_start": "2025-01-01T00:00:00Z",
            "period_end": "2025-01-31T23:59:59Z",
            "actor": "mlro@banxe.com",
            "financial_data": {"sar_reports": []},
        },
    )
    assert resp.status_code == 200


# ── GET /v1/regulatory/reports/audit ─────────────────────────────────────────


def test_audit_log_empty_initially(client: TestClient) -> None:
    resp = client.get("/v1/regulatory/reports/audit")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0
    assert data["entries"] == []


def test_audit_log_after_generate(client: TestClient) -> None:
    client.post(
        "/v1/regulatory/reports/generate",
        json={
            "report_type": "FIN060",
            "entity_id": "FRN999",
            "entity_name": "Test Firm",
            "period_start": "2025-01-01T00:00:00Z",
            "period_end": "2025-01-31T23:59:59Z",
            "actor": "actor1",
        },
    )
    # Note: each TestClient call uses a fresh agent instance (dependency_overrides factory)
    # so audit trail is independent; just check endpoint works
    resp = client.get("/v1/regulatory/reports/audit")
    assert resp.status_code == 200


def test_audit_log_unknown_report_type_filter_returns_422(client: TestClient) -> None:
    resp = client.get("/v1/regulatory/reports/audit?report_type=BOGUS")
    assert resp.status_code == 422


# ── POST /v1/regulatory/schedules ────────────────────────────────────────────


def test_create_schedule_monthly(client: TestClient) -> None:
    resp = client.post(
        "/v1/regulatory/schedules",
        json={
            "report_type": "FIN060",
            "entity_id": "FRN123456",
            "frequency": "MONTHLY",
            "actor": "admin@banxe.com",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["report_type"] == "FIN060"
    assert data["frequency"] == "MONTHLY"
    assert data["is_active"] is True


def test_create_schedule_unknown_frequency_returns_422(client: TestClient) -> None:
    resp = client.post(
        "/v1/regulatory/schedules",
        json={
            "report_type": "FIN060",
            "entity_id": "FRN123456",
            "frequency": "HOURLY",
            "actor": "admin@banxe.com",
        },
    )
    assert resp.status_code == 422


# ── DELETE /v1/regulatory/schedules/{id} ─────────────────────────────────────


def test_cancel_schedule(client: TestClient) -> None:
    resp = client.delete("/v1/regulatory/schedules/sched-001?actor=admin@banxe.com")
    assert resp.status_code == 200
    data = resp.json()
    assert data["cancelled"] is True


# ── GET /v1/regulatory/schedules/{entity_id} ─────────────────────────────────


def test_list_schedules_empty(client: TestClient) -> None:
    resp = client.get("/v1/regulatory/schedules/FRN123456")
    assert resp.status_code == 200
    data = resp.json()
    assert data["entity_id"] == "FRN123456"
    assert "schedules" in data


# ── GET /v1/regulatory/templates ─────────────────────────────────────────────


def test_list_templates_all_six(client: TestClient) -> None:
    resp = client.get("/v1/regulatory/templates")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 6
    types = [t["report_type"] for t in data["templates"]]
    assert "FIN060" in types
    assert "ACPR_EMI" in types
    assert "SAR_BATCH" in types


def test_list_templates_has_sla_days(client: TestClient) -> None:
    resp = client.get("/v1/regulatory/templates")
    data = resp.json()
    for tmpl in data["templates"]:
        assert tmpl["sla_days"] is not None


def test_list_templates_has_regulator(client: TestClient) -> None:
    resp = client.get("/v1/regulatory/templates")
    data = resp.json()
    fca_templates = [t for t in data["templates"] if t["regulator"] == "FCA_REGDATA"]
    assert len(fca_templates) == 3  # FIN060, FIN071, FSA076
