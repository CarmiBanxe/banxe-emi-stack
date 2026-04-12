"""
tests/test_transaction_monitor/test_api_routes.py
IL-RTM-01 | banxe-emi-stack

Tests for the 8 transaction monitor FastAPI endpoints.
Uses TestClient with InMemory dependency overrides.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from api.routers.transaction_monitor import (
    get_alert_store,
    get_generator,
    get_router_dep,
    get_scorer,
    get_velocity_tracker,
    router,
)
from services.transaction_monitor.alerts.alert_generator import AlertGenerator
from services.transaction_monitor.alerts.alert_router import AlertRouter, InMemoryMarblePort
from services.transaction_monitor.alerts.explanation_engine import InMemoryKBPort
from services.transaction_monitor.models.alert import AlertSeverity, AlertStatus, AMLAlert
from services.transaction_monitor.models.risk_score import RiskScore
from services.transaction_monitor.scoring.risk_scorer import InMemoryMLModel, RiskScorer
from services.transaction_monitor.scoring.velocity_tracker import InMemoryVelocityTracker
from services.transaction_monitor.store.alert_store import InMemoryAlertStore


@pytest.fixture
def app_with_overrides():
    """FastAPI app with all transaction monitor dependencies overridden."""
    store = InMemoryAlertStore()
    velocity = InMemoryVelocityTracker()
    marble = InMemoryMarblePort()

    scorer = RiskScorer(velocity_tracker=velocity, ml_model=InMemoryMLModel())
    generator = AlertGenerator(kb_port=InMemoryKBPort(), alert_store=store)
    alert_router = AlertRouter(marble_port=marble, alert_store=store)

    app = FastAPI()
    app.include_router(router)

    app.dependency_overrides[get_alert_store] = lambda: store
    app.dependency_overrides[get_velocity_tracker] = lambda: velocity
    app.dependency_overrides[get_scorer] = lambda: scorer
    app.dependency_overrides[get_generator] = lambda: generator
    app.dependency_overrides[get_router_dep] = lambda: alert_router

    return app, store, velocity, marble


def _make_alert(
    severity: AlertSeverity = AlertSeverity.HIGH,
    status: AlertStatus = AlertStatus.OPEN,
    customer_id: str = "cust-api-001",
) -> AMLAlert:
    rs = RiskScore(score=0.72)
    return AMLAlert(
        transaction_id="TXN-API-001",
        customer_id=customer_id,
        severity=severity,
        risk_score=rs,
        amount_gbp=Decimal("7500.00"),
        status=status,
    )


class TestHealthEndpoint:
    def test_health_returns_ok(self, app_with_overrides):
        app, *_ = app_with_overrides
        client = TestClient(app)
        response = client.get("/monitor/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "IL-RTM-01" in data["il"]


class TestScoreEndpoint:
    def test_score_transaction_returns_risk_and_alert(self, app_with_overrides):
        app, *_ = app_with_overrides
        client = TestClient(app)
        payload = {
            "transaction_id": "TXN-SCORE-001",
            "amount": "5000.00",
            "sender_id": "cust-score-001",
            "sender_jurisdiction": "GB",
        }
        response = client.post("/monitor/score", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["transaction_id"] == "TXN-SCORE-001"
        assert "risk_score" in data
        assert "alert" in data
        assert 0.0 <= data["risk_score"]["score"] <= 1.0

    def test_score_sanctioned_jurisdiction_is_critical(self, app_with_overrides):
        app, *_ = app_with_overrides
        client = TestClient(app)
        payload = {
            "transaction_id": "TXN-RU-001",
            "amount": "1000.00",
            "sender_id": "cust-ru",
            "sender_jurisdiction": "RU",
        }
        response = client.post("/monitor/score", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["risk_score"]["score"] == 1.0
        assert data["alert"]["severity"] == "critical"


class TestListAlertsEndpoint:
    def test_list_alerts_empty_initially(self, app_with_overrides):
        app, *_ = app_with_overrides
        client = TestClient(app)
        response = client.get("/monitor/alerts")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_alerts_returns_saved_alerts(self, app_with_overrides):
        app, store, *_ = app_with_overrides
        store.save(_make_alert(AlertSeverity.HIGH))
        store.save(_make_alert(AlertSeverity.MEDIUM))
        client = TestClient(app)
        response = client.get("/monitor/alerts")
        assert response.status_code == 200
        assert len(response.json()) == 2

    def test_list_alerts_filter_by_severity(self, app_with_overrides):
        app, store, *_ = app_with_overrides
        store.save(_make_alert(AlertSeverity.CRITICAL))
        store.save(_make_alert(AlertSeverity.LOW))
        client = TestClient(app)
        response = client.get("/monitor/alerts?severity=critical")
        assert response.status_code == 200
        results = response.json()
        assert all(r["severity"] == "critical" for r in results)

    def test_list_alerts_invalid_severity_returns_400(self, app_with_overrides):
        app, *_ = app_with_overrides
        client = TestClient(app)
        response = client.get("/monitor/alerts?severity=bogus")
        assert response.status_code == 400


class TestGetAlertEndpoint:
    def test_get_alert_returns_detail(self, app_with_overrides):
        app, store, *_ = app_with_overrides
        alert = _make_alert()
        store.save(alert)
        client = TestClient(app)
        response = client.get(f"/monitor/alerts/{alert.alert_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["alert_id"] == alert.alert_id
        assert data["customer_id"] == "cust-api-001"

    def test_get_alert_not_found_returns_404(self, app_with_overrides):
        app, *_ = app_with_overrides
        client = TestClient(app)
        response = client.get("/monitor/alerts/ALT-DOESNOTEXIST")
        assert response.status_code == 404


class TestUpdateAlertEndpoint:
    def test_patch_alert_updates_status(self, app_with_overrides):
        app, store, *_ = app_with_overrides
        alert = _make_alert(AlertSeverity.MEDIUM, AlertStatus.OPEN)
        store.save(alert)
        client = TestClient(app)
        response = client.patch(
            f"/monitor/alerts/{alert.alert_id}",
            json={"status": "reviewing"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "reviewing"

    def test_patch_critical_alert_close_without_notes_returns_422(self, app_with_overrides):
        app, store, *_ = app_with_overrides
        alert = _make_alert(AlertSeverity.CRITICAL, AlertStatus.ESCALATED)
        store.save(alert)
        client = TestClient(app)
        response = client.patch(
            f"/monitor/alerts/{alert.alert_id}",
            json={"status": "closed", "notes": ""},
        )
        assert response.status_code == 422

    def test_patch_critical_alert_close_with_notes_succeeds(self, app_with_overrides):
        app, store, *_ = app_with_overrides
        alert = _make_alert(AlertSeverity.CRITICAL, AlertStatus.ESCALATED)
        store.save(alert)
        client = TestClient(app)
        response = client.patch(
            f"/monitor/alerts/{alert.alert_id}",
            json={"status": "closed", "notes": "MLRO sign-off confirmed: case resolved."},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "closed"


class TestVelocityEndpoint:
    def test_get_velocity_returns_metrics(self, app_with_overrides):
        app, *_ = app_with_overrides
        client = TestClient(app)
        response = client.get("/monitor/velocity/cust-vel-001")
        assert response.status_code == 200
        data = response.json()
        assert data["customer_id"] == "cust-vel-001"
        assert "velocity" in data
        assert "1h" in data["velocity"]
        assert "24h" in data["velocity"]
        assert "requires_edd" in data


class TestMetricsEndpoint:
    def test_get_metrics_returns_dashboard_data(self, app_with_overrides):
        app, store, *_ = app_with_overrides
        store.save(_make_alert(AlertSeverity.CRITICAL))
        store.save(_make_alert(AlertSeverity.HIGH))
        client = TestClient(app)
        response = client.get("/monitor/metrics")
        assert response.status_code == 200
        data = response.json()
        assert "total_alerts" in data
        assert "by_severity" in data
        assert data["total_alerts"] == 2


class TestBacktestEndpoint:
    def test_post_backtest_returns_result(self, app_with_overrides):
        app, *_ = app_with_overrides
        client = TestClient(app)
        payload = {
            "from_date": "2026-01-01T00:00:00",
            "to_date": "2026-01-31T23:59:59",
            "sample_size": 10,
        }
        response = client.post("/monitor/backtest", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["total_transactions"] == 10
        assert "hit_rate" in data
        assert "sar_yield_estimate" in data
        assert 0.0 <= data["hit_rate"] <= 1.0
