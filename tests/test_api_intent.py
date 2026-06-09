"""
tests/test_api_intent.py — HTTP tests for the L1 Intent Layer entrypoint (S8).

Exercises POST /v1/intent + GET /v1/intent/decision/{id} through FastAPI's
TestClient with the in-memory composition (NullLLM, Null L3 producers, in-memory
sink). Proves the gate (INTENT_LAYER_ENABLED), the in-process real-mask dispatch
(Notifications → NotificationAgent), the governance-event path, the honest
unrouted path (Payments — owned by banxe-payment-core), and lineage retrieval.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from api.main import app

client = TestClient(app)


@pytest.fixture()
def enabled(monkeypatch) -> None:
    monkeypatch.setenv("INTENT_LAYER_ENABLED", "true")


@pytest.fixture()
def disabled(monkeypatch) -> None:
    monkeypatch.setenv("INTENT_LAYER_ENABLED", "false")


def test_disabled_returns_not_enabled_no_dispatch(disabled):
    resp = client.post(
        "/v1/intent", json={"intent_text": "notifications", "correlation_id": "c-off-1"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is False
    assert body["disposition"] == "NOT_ENABLED"
    assert body["decision_record"] is None
    # No record was emitted while disabled.
    assert client.get("/v1/intent/decision/c-off-1").status_code == 404


def test_enabled_notifications_dispatches_real_mask(enabled):
    resp = client.post(
        "/v1/intent", json={"intent_text": "notifications", "correlation_id": "c-notif-1"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is True
    assert body["disposition"] == "DISPATCHED"
    record = body["decision_record"]
    assert record is not None
    assert record["agent_id"] == "notification_agent"
    assert record["action_taken"] == "CHECK_CHANNEL_AVAILABLE"
    assert record["compliance_result"] == "PASS"
    # cost_amount is a Decimal STRING — never a float (I-05).
    assert isinstance(record["cost_amount"], str)


def test_get_decision_retrieves_emitted_record(enabled):
    client.post("/v1/intent", json={"intent_text": "alerts", "correlation_id": "c-get-1"})
    resp = client.get("/v1/intent/decision/c-get-1")
    assert resp.status_code == 200
    assert resp.json()["correlation_id"] == "c-get-1"


def test_unresolved_intent_returns_governance_event(enabled):
    resp = client.post(
        "/v1/intent", json={"intent_text": "zxcvbnm nonsense", "correlation_id": "c-unres-1"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["disposition"] == "GOVERNANCE_EVENT"
    assert body["decision_record"] is None
    assert body["governance_event"]["status"] == "UNRESOLVED"


def test_payments_is_unrouted_in_process(enabled):
    """Payments is owned by banxe-payment-core — honestly unrouted in-process, no record."""
    resp = client.post("/v1/intent", json={"intent_text": "pay", "correlation_id": "c-pay-1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["disposition"] == "DISPATCHED"
    assert body["decision_record"] is None
    assert "no in-process L2 mask" in body["detail"]


def test_get_decision_missing_returns_404(enabled):
    assert client.get("/v1/intent/decision/does-not-exist").status_code == 404


def test_empty_intent_text_is_rejected(enabled):
    assert client.post("/v1/intent", json={"intent_text": ""}).status_code == 422
