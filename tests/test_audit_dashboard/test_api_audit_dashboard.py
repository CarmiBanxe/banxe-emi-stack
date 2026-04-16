"""
tests/test_audit_dashboard/test_api_audit_dashboard.py
IL-AGD-01 | Phase 16

Integration tests for /v1/audit/* endpoints.
Uses FastAPI TestClient with the audit_dashboard router mounted under /v1.
Each test uses a fresh _get_services via patch to avoid lru_cache sharing.
"""

from __future__ import annotations

from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from api.routers.audit_dashboard import router
from services.audit_dashboard.audit_aggregator import AuditAggregator
from services.audit_dashboard.dashboard_api import DashboardService
from services.audit_dashboard.governance_reporter import GovernanceReporter
from services.audit_dashboard.models import (
    InMemoryEventStore,
    InMemoryMetricsStore,
    InMemoryReportStore,
    InMemoryRiskEngine,
)
from services.audit_dashboard.risk_scorer import RiskScorer

# ── Local test app ────────────────────────────────────────────────────────────

_test_app = FastAPI()
_test_app.include_router(router, prefix="/v1")


def _make_fresh_services():
    store = InMemoryEventStore()
    report_store = InMemoryReportStore()
    risk_engine = InMemoryRiskEngine()
    metrics_store = InMemoryMetricsStore()

    aggregator = AuditAggregator(store=store)
    scorer = RiskScorer(engine=risk_engine, store=store)
    reporter = GovernanceReporter(
        aggregator=aggregator,
        scorer=scorer,
        report_store=report_store,
    )
    dashboard = DashboardService(
        aggregator=aggregator,
        scorer=scorer,
        reporter=reporter,
        metrics_store=metrics_store,
    )
    return aggregator, scorer, reporter, dashboard


@pytest.fixture()
def client():
    """TestClient with a fresh (shared) InMemory service graph per test."""
    services = _make_fresh_services()
    with patch("api.routers.audit_dashboard._get_services", return_value=services):
        yield TestClient(_test_app)


# ── POST /v1/audit/events ─────────────────────────────────────────────────────


def test_post_audit_event_returns_200_with_id(client):
    resp = client.post(
        "/v1/audit/events",
        json={
            "category": "AML",
            "event_type": "threshold_check",
            "entity_id": "cust-001",
            "actor": "system",
            "details": {"note": "test"},
            "risk_level": "LOW",
            "source_service": "aml-service",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert data["category"] == "AML"


def test_post_audit_event_aml_category(client):
    resp = client.post(
        "/v1/audit/events",
        json={
            "category": "AML",
            "event_type": "sar_candidate",
            "entity_id": "cust-aml",
            "actor": "mlro",
            "risk_level": "HIGH",
            "source_service": "aml-engine",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["risk_level"] == "HIGH"


def test_post_audit_event_invalid_category_returns_422(client):
    resp = client.post(
        "/v1/audit/events",
        json={
            "category": "NOT_A_CATEGORY",
            "event_type": "test",
            "entity_id": "e",
            "actor": "a",
            "risk_level": "LOW",
            "source_service": "svc",
        },
    )
    assert resp.status_code == 422


# ── GET /v1/audit/events ──────────────────────────────────────────────────────


def test_get_audit_events_returns_200_list(client):
    resp = client.get("/v1/audit/events")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_audit_events_filter_by_category(client):
    resp = client.get("/v1/audit/events?category=AML")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_audit_events_filter_by_entity_id(client):
    resp = client.get("/v1/audit/events?entity_id=entity-001")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ── Ingest then query ─────────────────────────────────────────────────────────


def test_ingest_event_then_query_event_found(client):
    # Ingest
    client.post(
        "/v1/audit/events",
        json={
            "category": "PAYMENT",
            "event_type": "payment_initiated",
            "entity_id": "cust-find-me",
            "actor": "user",
            "risk_level": "LOW",
            "source_service": "payment-svc",
        },
    )
    # Query
    resp = client.get("/v1/audit/events?entity_id=cust-find-me")
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 1
    assert results[0]["entity_id"] == "cust-find-me"


# ── GET /v1/audit/risk/score/{entity_id} ─────────────────────────────────────


def test_get_risk_score_returns_200(client):
    resp = client.get("/v1/audit/risk/score/entity-001")
    assert resp.status_code == 200
    data = resp.json()
    assert "entity_id" in data
    assert "overall_score" in data


# ── POST /v1/audit/reports ────────────────────────────────────────────────────


def test_post_generate_report_returns_200(client):
    resp = client.post(
        "/v1/audit/reports",
        json={
            "title": "Q1 Governance Report",
            "period_start": "2026-01-01T00:00:00Z",
            "period_end": "2026-03-31T23:59:59Z",
            "entity_ids": [],
            "actor": "compliance-officer",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert data["title"] == "Q1 Governance Report"


# ── GET /v1/audit/reports ─────────────────────────────────────────────────────


def test_get_list_reports_returns_200(client):
    resp = client.get("/v1/audit/reports")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ── GET /v1/audit/reports/{id} ────────────────────────────────────────────────


def test_get_report_by_id_after_generating(client):
    create_resp = client.post(
        "/v1/audit/reports",
        json={
            "title": "Fetch Test Report",
            "period_start": "2026-01-01T00:00:00Z",
            "period_end": "2026-01-31T23:59:59Z",
        },
    )
    report_id = create_resp.json()["id"]
    resp = client.get(f"/v1/audit/reports/{report_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == report_id


def test_get_report_unknown_id_returns_404(client):
    resp = client.get("/v1/audit/reports/unknown-id-that-doesnt-exist")
    assert resp.status_code == 404


# ── GET /v1/audit/dashboard/metrics ──────────────────────────────────────────


def test_get_dashboard_metrics_returns_200(client):
    resp = client.get("/v1/audit/dashboard/metrics")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_events_24h" in data
    assert "compliance_score" in data


# ── GET /v1/audit/governance/status ──────────────────────────────────────────


def test_get_governance_status_returns_200_with_status(client):
    resp = client.get("/v1/audit/governance/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data


def test_get_governance_status_has_checked_at(client):
    resp = client.get("/v1/audit/governance/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "checked_at" in data
