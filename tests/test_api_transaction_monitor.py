"""
tests/test_api_transaction_monitor.py — Transaction Monitor router tests
S13-06-FIX-2 | banxe-emi-stack

Tests for GET/POST /v1/monitor/* endpoints (transaction_monitor.py 34% → ≥85%).
Mocks all 5 DI providers via app.dependency_overrides.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
import pytest

from api.main import app
from api.routers.transaction_monitor import (
    get_alert_store,
    get_generator,
    get_router_dep,
    get_scorer,
    get_velocity_tracker,
)
from services.transaction_monitor.models.alert import (
    AlertSeverity,
    AlertStatus,
    AMLAlert,
)
from services.transaction_monitor.models.risk_score import RiskScore

client = TestClient(app)


# ── Helpers ────────────────────────────────────────────────────────────────


def _make_risk_score(score: float = 0.5) -> RiskScore:
    return RiskScore(score=score)


def _make_alert(
    alert_id: str = "ALT-TEST0001",
    severity: AlertSeverity = AlertSeverity.HIGH,
    status: AlertStatus = AlertStatus.OPEN,
) -> AMLAlert:
    return AMLAlert(
        alert_id=alert_id,
        transaction_id="TX-001",
        customer_id="cust-001",
        severity=severity,
        risk_score=_make_risk_score(0.7),
        amount_gbp=Decimal("500.00"),
        status=status,
    )


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture()
def mock_store():
    m = MagicMock()
    m.list_alerts.return_value = [_make_alert()]
    m.get.return_value = _make_alert()
    m.save.return_value = None
    m.count_by_severity.return_value = {"low": 2, "medium": 3, "high": 1, "critical": 0}
    return m


@pytest.fixture()
def mock_velocity():
    m = MagicMock()
    m.get_count.return_value = 3
    m.get_cumulative_amount.return_value = Decimal("1500.00")
    m.requires_edd.return_value = False
    return m


@pytest.fixture()
def mock_scorer():
    m = MagicMock()
    m.score.return_value = _make_risk_score(0.5)
    return m


@pytest.fixture()
def mock_generator():
    m = MagicMock()
    m.generate.return_value = _make_alert()
    return m


@pytest.fixture()
def mock_alert_router():
    m = MagicMock()
    m.route.return_value = _make_alert()
    return m


@pytest.fixture(autouse=True)
def setup_overrides(mock_store, mock_velocity, mock_scorer, mock_generator, mock_alert_router):
    app.dependency_overrides[get_alert_store] = lambda: mock_store
    app.dependency_overrides[get_velocity_tracker] = lambda: mock_velocity
    app.dependency_overrides[get_scorer] = lambda: mock_scorer
    app.dependency_overrides[get_generator] = lambda: mock_generator
    app.dependency_overrides[get_router_dep] = lambda: mock_alert_router
    yield
    for dep in [get_alert_store, get_velocity_tracker, get_scorer, get_generator, get_router_dep]:
        app.dependency_overrides.pop(dep, None)


# ── Health ─────────────────────────────────────────────────────────────────


def test_monitor_health_returns_200():
    resp = client.get("/v1/monitor/health")
    assert resp.status_code == 200


def test_monitor_health_response_structure():
    resp = client.get("/v1/monitor/health")
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "transaction_monitor"


# ── Score ──────────────────────────────────────────────────────────────────


def test_score_transaction_returns_200(mock_scorer, mock_generator, mock_alert_router):
    mock_scorer.score.return_value = _make_risk_score(0.5)
    mock_generator.generate.return_value = _make_alert()
    mock_alert_router.route.return_value = _make_alert()
    resp = client.post(
        "/v1/monitor/score",
        json={
            "transaction_id": "TX-001",
            "amount": "500.00",
            "sender_id": "cust-001",
        },
    )
    assert resp.status_code == 200


def test_score_response_has_expected_fields(mock_scorer, mock_generator, mock_alert_router):
    mock_scorer.score.return_value = _make_risk_score(0.5)
    mock_generator.generate.return_value = _make_alert()
    mock_alert_router.route.return_value = _make_alert()
    resp = client.post(
        "/v1/monitor/score",
        json={"transaction_id": "TX-001", "amount": "500.00", "sender_id": "cust-001"},
    )
    data = resp.json()
    assert "transaction_id" in data
    assert "risk_score" in data
    assert "alert" in data


def test_score_internal_error_returns_500(mock_scorer):
    mock_scorer.score.side_effect = Exception("ML model unavailable")
    resp = client.post(
        "/v1/monitor/score",
        json={"transaction_id": "TX-ERR", "amount": "100.00", "sender_id": "cust-002"},
    )
    assert resp.status_code == 500


# ── List alerts ────────────────────────────────────────────────────────────


def test_list_alerts_returns_200():
    resp = client.get("/v1/monitor/alerts")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_list_alerts_filter_by_severity_high():
    resp = client.get("/v1/monitor/alerts?severity=high")
    assert resp.status_code == 200


def test_list_alerts_filter_by_invalid_severity_returns_400():
    resp = client.get("/v1/monitor/alerts?severity=not_a_severity")
    assert resp.status_code == 400


def test_list_alerts_filter_by_status_open():
    resp = client.get("/v1/monitor/alerts?status=open")
    assert resp.status_code == 200


def test_list_alerts_filter_by_invalid_status_returns_400():
    resp = client.get("/v1/monitor/alerts?status=bogus_status")
    assert resp.status_code == 400


def test_list_alerts_filter_by_customer_id():
    resp = client.get("/v1/monitor/alerts?customer_id=cust-001")
    assert resp.status_code == 200


# ── Get alert ──────────────────────────────────────────────────────────────


def test_get_alert_found_returns_200():
    resp = client.get("/v1/monitor/alerts/ALT-TEST0001")
    assert resp.status_code == 200
    assert resp.json()["alert_id"] == "ALT-TEST0001"


def test_get_alert_not_found_returns_404(mock_store):
    mock_store.get.return_value = None
    resp = client.get("/v1/monitor/alerts/no-such-alert")
    assert resp.status_code == 404


# ── Update alert ───────────────────────────────────────────────────────────


def test_update_alert_status_returns_200(mock_store):
    mock_store.get.return_value = _make_alert()
    resp = client.patch(
        "/v1/monitor/alerts/ALT-TEST0001",
        json={"status": "reviewing"},
    )
    assert resp.status_code == 200


def test_update_alert_not_found_returns_404(mock_store):
    mock_store.get.return_value = None
    resp = client.patch(
        "/v1/monitor/alerts/no-such",
        json={"status": "reviewing"},
    )
    assert resp.status_code == 404


def test_update_critical_alert_no_notes_returns_422(mock_store):
    critical = _make_alert(alert_id="ALT-CRIT0001", severity=AlertSeverity.CRITICAL)
    mock_store.get.return_value = critical
    resp = client.patch(
        "/v1/monitor/alerts/ALT-CRIT0001",
        json={"status": "closed", "notes": ""},
    )
    assert resp.status_code == 422
    assert "CRITICAL" in resp.json()["detail"]


def test_update_critical_alert_with_notes_returns_200(mock_store):
    critical = _make_alert(alert_id="ALT-CRIT0001", severity=AlertSeverity.CRITICAL)
    mock_store.get.return_value = critical
    resp = client.patch(
        "/v1/monitor/alerts/ALT-CRIT0001",
        json={"status": "closed", "notes": "MLRO reviewed and approved closure — SAR filed."},
    )
    assert resp.status_code == 200


# ── Velocity ───────────────────────────────────────────────────────────────


def test_get_velocity_returns_200():
    resp = client.get("/v1/monitor/velocity/cust-001")
    assert resp.status_code == 200


def test_get_velocity_response_structure():
    resp = client.get("/v1/monitor/velocity/cust-001")
    data = resp.json()
    assert data["customer_id"] == "cust-001"
    assert "velocity" in data
    assert "1h" in data["velocity"]
    assert "24h" in data["velocity"]
    assert "7d" in data["velocity"]
    assert "requires_edd" in data


# ── Metrics ────────────────────────────────────────────────────────────────


def test_get_metrics_returns_200(mock_store):
    mock_store.list_alerts.return_value = []
    resp = client.get("/v1/monitor/metrics")
    assert resp.status_code == 200


def test_get_metrics_response_has_expected_fields(mock_store):
    mock_store.list_alerts.return_value = []
    resp = client.get("/v1/monitor/metrics")
    data = resp.json()
    assert "total_alerts" in data
    assert "by_severity" in data
    assert "open_alerts" in data
    assert "sar_yield_estimate" in data


def test_get_metrics_with_existing_alerts(mock_store):
    mock_store.list_alerts.return_value = [_make_alert()]
    mock_store.count_by_severity.return_value = {"high": 1, "critical": 0, "medium": 0, "low": 0}
    resp = client.get("/v1/monitor/metrics")
    assert resp.status_code == 200


# ── Backtest ───────────────────────────────────────────────────────────────


def test_backtest_returns_200(mock_scorer):
    mock_scorer.score.return_value = _make_risk_score(0.5)
    resp = client.post(
        "/v1/monitor/backtest",
        json={
            "from_date": "2026-01-01T00:00:00",
            "to_date": "2026-03-31T23:59:59",
            "sample_size": 10,
        },
    )
    assert resp.status_code == 200


def test_backtest_response_has_expected_fields(mock_scorer):
    mock_scorer.score.return_value = _make_risk_score(0.5)
    resp = client.post(
        "/v1/monitor/backtest",
        json={
            "from_date": "2026-01-01T00:00:00",
            "to_date": "2026-03-31T23:59:59",
            "sample_size": 5,
        },
    )
    data = resp.json()
    assert "total_transactions" in data
    assert "alerts_generated" in data
    assert "hit_rate" in data
    assert "sar_yield_estimate" in data
