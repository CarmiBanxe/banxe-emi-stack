"""
tests/test_watchman_webhook.py — Watchman webhook endpoint tests
IL-068 | AML/Compliance block | banxe-emi-stack

Tests: secret validation, health ping, list_updated event, n8n trigger failure.
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)

VALID_SECRET = "test-watchman-secret"

_LIST_UPDATED = {
    "type": "list_updated",
    "list": "ofac_sdn",
    "timestamp": "2026-04-09T05:00:00Z",
    "details": None,
}

_HEALTH_PING = {
    "type": "health",
    "timestamp": "2026-04-09T05:00:00Z",
}

_SEARCH_NOTIFICATION = {
    "type": "search_notification",
    "list": None,
    "timestamp": "2026-04-09T05:01:00Z",
}


@pytest.fixture(autouse=True)
def set_watchman_secret(monkeypatch):
    monkeypatch.setenv("WATCHMAN_WEBHOOK_SECRET", VALID_SECRET)
    yield
    # clear processor secret cache so it re-reads env each test
    from api.routers.watchman_webhook import _processor
    _processor._secrets["watchman"] = os.environ.get("WATCHMAN_WEBHOOK_SECRET", "")


def _post(payload: dict, secret: str = VALID_SECRET) -> object:
    return client.post(
        "/webhooks/watchman",
        json=payload,
        headers={"X-Watchman-Secret": secret},
    )


class TestWatchmanWebhookSecurity:
    def test_missing_secret_returns_401(self):
        resp = client.post("/webhooks/watchman", json=_LIST_UPDATED)
        assert resp.status_code == 401

    def test_wrong_secret_returns_401(self):
        resp = _post(_LIST_UPDATED, secret="wrong-secret")
        assert resp.status_code == 401

    def test_valid_secret_returns_202(self):
        resp = _post(_LIST_UPDATED)
        assert resp.status_code == 202

    def test_no_secret_env_accepts_any(self, monkeypatch):
        """If WATCHMAN_WEBHOOK_SECRET is unset, endpoint accepts any secret."""
        monkeypatch.delenv("WATCHMAN_WEBHOOK_SECRET", raising=False)
        from api.routers.watchman_webhook import _processor
        _processor._secrets["watchman"] = ""
        resp = client.post("/webhooks/watchman", json=_LIST_UPDATED)
        assert resp.status_code == 202


class TestWatchmanWebhookEvents:
    def test_health_ping_accepted(self):
        resp = _post(_HEALTH_PING)
        assert resp.status_code == 202
        body = resp.json()
        assert body["event_type"] == "health"
        assert body["n8n_triggered"] is False

    def test_list_updated_accepted(self):
        resp = _post(_LIST_UPDATED)
        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == "accepted"
        assert body["event_type"] == "list_updated"
        assert body["list_name"] == "ofac_sdn"

    def test_search_notification_accepted(self):
        resp = _post(_SEARCH_NOTIFICATION)
        assert resp.status_code == 202
        body = resp.json()
        assert body["event_type"] == "search_notification"

    def test_response_has_n8n_triggered_field(self):
        resp = _post(_LIST_UPDATED)
        assert "n8n_triggered" in resp.json()

    def test_invalid_type_returns_422(self):
        bad = {**_LIST_UPDATED, "type": "unknown_event"}
        resp = _post(bad)
        assert resp.status_code == 422

    def test_missing_timestamp_returns_422(self):
        bad = {"type": "list_updated", "list": "ofac_sdn"}
        resp = _post(bad)
        assert resp.status_code == 422

    def test_health_ping_does_not_trigger_n8n(self):
        """Health pings must never trigger n8n workflows."""
        resp = _post(_HEALTH_PING)
        assert resp.json()["n8n_triggered"] is False
