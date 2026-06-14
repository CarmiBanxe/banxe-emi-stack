"""
tests/test_canary_api.py — FU-2 Phase 5 canary, end-to-end over the HTTP surface.

Exercises the staging canary through POST /v1/intent + GET /v1/intent/canary/metrics:
  • a staging-like config (APP_ENV=staging + per-env enable + Notifications allowlist)
    routes Notifications through the layer and records a decision,
  • no other capability is auto-dispatched (high-risk → governance, others → dark),
  • enabled-but-no-allowlist (a leaked global flag) dispatches NOTHING (default-deny),
  • a staging override never enables the layer in production,
  • the canary metrics counters move.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from api.main import app

client = TestClient(app)


@pytest.fixture()
def staging_canary(monkeypatch) -> None:
    """The exact env an operator sets to light the staging canary (env-only)."""
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("INTENT_LAYER_ENABLED_STAGING", "true")
    monkeypatch.setenv("INTENT_LAYER_CANARY_CAPABILITIES", "Notifications")
    monkeypatch.delenv("INTENT_LAYER_ENABLED", raising=False)


def test_staging_canary_dispatches_notifications(staging_canary):
    resp = client.post(
        "/v1/intent", json={"intent_text": "notifications", "correlation_id": "c-canary-1"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is True
    assert body["disposition"] == "DISPATCHED"
    assert body["decision_record"]["agent_id"] == "notification_agent"
    # A lineage record was recorded for the canary intent.
    assert client.get("/v1/intent/decision/c-canary-1").status_code == 200


def test_staging_canary_withholds_high_risk_fx(staging_canary):
    resp = client.post("/v1/intent", json={"intent_text": "fx", "correlation_id": "c-fx-1"})
    body = resp.json()
    assert body["disposition"] == "GOVERNANCE_EVENT"
    assert "high-risk" in body["governance_event"]["reason"]
    assert client.get("/v1/intent/decision/c-fx-1").status_code == 404


def test_staging_canary_withholds_high_risk_kyc(staging_canary):
    resp = client.post(
        "/v1/intent", json={"intent_text": "complete KYC", "correlation_id": "c-kyc-1"}
    )
    assert resp.json()["disposition"] == "GOVERNANCE_EVENT"


def test_staging_canary_withholds_other_low_risk_capability(staging_canary):
    # Statements is low-risk but outside the canary scope → safe dark-mode no-op.
    resp = client.post(
        "/v1/intent", json={"intent_text": "statement", "correlation_id": "c-stmt-1"}
    )
    body = resp.json()
    assert body["disposition"] == "NOT_ENABLED"
    assert body["decision_record"] is None


def test_enabled_without_allowlist_dispatches_nothing(monkeypatch):
    # A leaked global flag with NO allowlist must dispatch nothing (default-deny).
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("INTENT_LAYER_ENABLED_STAGING", "true")
    monkeypatch.delenv("INTENT_LAYER_CANARY_CAPABILITIES", raising=False)
    resp = client.post(
        "/v1/intent", json={"intent_text": "notifications", "correlation_id": "c-deny-1"}
    )
    body = resp.json()
    assert body["disposition"] == "NOT_ENABLED"
    assert body["decision_record"] is None


def test_staging_override_does_not_leak_into_production(monkeypatch):
    # APP_ENV=production with only the staging override set → layer stays dark.
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("INTENT_LAYER_ENABLED_STAGING", "true")
    monkeypatch.setenv("INTENT_LAYER_CANARY_CAPABILITIES", "Notifications")
    monkeypatch.delenv("INTENT_LAYER_ENABLED", raising=False)
    resp = client.post(
        "/v1/intent", json={"intent_text": "notifications", "correlation_id": "c-prod-1"}
    )
    body = resp.json()
    assert body["enabled"] is False
    assert body["disposition"] == "NOT_ENABLED"


def test_canary_metrics_endpoint_counts_decisions(staging_canary):
    before = client.get("/v1/intent/canary/metrics").json()
    client.post("/v1/intent", json={"intent_text": "notifications", "correlation_id": "c-m-1"})
    client.post("/v1/intent", json={"intent_text": "fx", "correlation_id": "c-m-2"})
    after = client.get("/v1/intent/canary/metrics").json()
    assert after["canary_intents_total"] >= before["canary_intents_total"] + 2
    assert after["canary_dispatched"] >= before["canary_dispatched"] + 1
    assert after["canary_withheld_high_risk"] >= before["canary_withheld_high_risk"] + 1
