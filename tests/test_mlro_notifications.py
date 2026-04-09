"""
tests/test_mlro_notifications.py — MLRO notification endpoint tests
IL-068 | AML/Compliance block | banxe-emi-stack
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.routers.mlro_notifications import clear_notification_log, get_notification_log

client = TestClient(app)

VALID_TOKEN = "test-internal-token"

_AML_ALERT = {
    "channel": "mlro_aml_alerts",
    "message": "High-risk SAR-relevant alert detected",
    "source": "banxe_aml_orchestrator",
    "severity": "critical",
}

_SANCTIONS_WARN = {
    "channel": "mlro_sanctions",
    "message": "Watchman list updated: ofac_sdn",
    "source": "watchman_list_update",
    "severity": "warning",
}


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_TOKEN", VALID_TOKEN)
    clear_notification_log()
    yield
    clear_notification_log()


def _post(payload: dict, token: str = VALID_TOKEN) -> object:
    return client.post(
        "/internal/notifications/mlro",
        json=payload,
        headers={"X-Internal-Token": token},
    )


class TestMLRONotificationSecurity:
    def test_missing_token_returns_401(self):
        resp = client.post("/internal/notifications/mlro", json=_AML_ALERT)
        assert resp.status_code == 401

    def test_wrong_token_returns_401(self):
        resp = _post(_AML_ALERT, token="wrong")
        assert resp.status_code == 401

    def test_valid_token_returns_202(self):
        resp = _post(_AML_ALERT)
        assert resp.status_code == 202

    def test_no_token_env_accepts_any(self, monkeypatch):
        monkeypatch.delenv("INTERNAL_API_TOKEN", raising=False)
        resp = client.post("/internal/notifications/mlro", json=_AML_ALERT)
        assert resp.status_code == 202


class TestMLRONotificationPayload:
    def test_response_has_notification_id(self):
        resp = _post(_AML_ALERT)
        assert "notification_id" in resp.json()
        assert len(resp.json()["notification_id"]) == 36  # UUID

    def test_response_has_status_accepted(self):
        resp = _post(_AML_ALERT)
        assert resp.json()["status"] == "accepted"

    def test_response_reflects_channel(self):
        resp = _post(_SANCTIONS_WARN)
        assert resp.json()["channel"] == "mlro_sanctions"

    def test_response_reflects_severity(self):
        resp = _post(_AML_ALERT)
        assert resp.json()["severity"] == "critical"

    def test_response_has_logged_at(self):
        resp = _post(_AML_ALERT)
        assert "logged_at" in resp.json()

    def test_invalid_channel_returns_422(self):
        bad = {**_AML_ALERT, "channel": "unknown_channel"}
        resp = _post(bad)
        assert resp.status_code == 422

    def test_invalid_severity_returns_422(self):
        bad = {**_AML_ALERT, "severity": "extreme"}
        resp = _post(bad)
        assert resp.status_code == 422


class TestMLRONotificationAuditLog:
    def test_notification_logged(self):
        _post(_AML_ALERT)
        log = get_notification_log()
        assert len(log) == 1
        assert log[0]["channel"] == "mlro_aml_alerts"
        assert log[0]["severity"] == "critical"

    def test_multiple_notifications_all_logged(self):
        _post(_AML_ALERT)
        _post(_SANCTIONS_WARN)
        log = get_notification_log()
        assert len(log) == 2

    def test_notification_id_in_log(self):
        resp = _post(_AML_ALERT)
        notification_id = resp.json()["notification_id"]
        log = get_notification_log()
        assert log[0]["notification_id"] == notification_id

    def test_source_logged(self):
        _post(_AML_ALERT)
        log = get_notification_log()
        assert log[0]["source"] == "banxe_aml_orchestrator"

    def test_failed_auth_not_logged(self):
        _post(_AML_ALERT, token="wrong")
        log = get_notification_log()
        assert len(log) == 0
