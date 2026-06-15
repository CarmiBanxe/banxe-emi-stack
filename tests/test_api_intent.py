"""
tests/test_api_intent.py — HTTP tests for the L1 Intent Layer entrypoint (S8).

Exercises POST /v1/intent + GET /v1/intent/decision/{id} through FastAPI's
TestClient with the in-memory composition (NullLLM, Null L3 producers, in-memory
sink). Proves the gate (INTENT_LAYER_ENABLED), the in-process real-mask dispatch
(Notifications + Referral / CRM — the FU-2 Phase 7 canary scope), the governance-event
path, the held-out scope guard (Payments — high-risk, mechanically blocked), and
lineage retrieval.

The ``enabled`` fixture activates the canary the way staging does: the flag ON,
``BANXE_ENV=staging`` and the Phase 7 ``INTENT_LAYER_CANARY_CAPABILITIES`` allow-list.
Without ``BANXE_ENV=staging`` the allow-list is empty (prod stays dark) — proven by
``test_non_staging_holds_even_when_enabled``.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from api.main import app

client = TestClient(app)

# The Phase 7 staging canary scope: Notifications + Referral / CRM (both low-risk).
_STAGING_CANARY_CAPS = "Notifications,Referral / CRM"


@pytest.fixture()
def enabled(monkeypatch) -> None:
    monkeypatch.setenv("INTENT_LAYER_ENABLED", "true")
    monkeypatch.setenv("BANXE_ENV", "staging")
    monkeypatch.setenv("INTENT_LAYER_CANARY_CAPABILITIES", _STAGING_CANARY_CAPS)


@pytest.fixture()
def disabled(monkeypatch) -> None:
    monkeypatch.setenv("INTENT_LAYER_ENABLED", "false")
    monkeypatch.setenv("BANXE_ENV", "staging")
    monkeypatch.setenv("INTENT_LAYER_CANARY_CAPABILITIES", _STAGING_CANARY_CAPS)


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


def test_referral_crm_dispatches_real_mask(enabled):
    """FU-2 Phase 7: Referral / CRM is the one low-risk capability the canary widens to —
    its read path (resolve_referral_code) dispatches to the real CRMAgent mask."""
    resp = client.post("/v1/intent", json={"intent_text": "refer", "correlation_id": "c-crm-1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is True
    assert body["disposition"] == "DISPATCHED"
    record = body["decision_record"]
    assert record is not None
    assert record["agent_id"] == "crm_agent"
    assert record["action_taken"] == "RESOLVE_REFERRAL_CODE"
    assert record["compliance_result"] == "PASS"


def test_payments_is_held_high_risk_never_dispatched(enabled):
    """Payments is high-risk (money movement) — mechanically held out of the canary even
    while enabled in staging. No dispatch, no in-process mask, no lineage record."""
    resp = client.post("/v1/intent", json={"intent_text": "pay", "correlation_id": "c-pay-1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is True
    assert body["disposition"] == "CANARY_HELD"
    assert body["decision_record"] is None
    assert "outside the staging canary allow-list" in body["detail"]
    # Nothing was recorded for a held intent.
    assert client.get("/v1/intent/decision/c-pay-1").status_code == 404


@pytest.mark.parametrize("intent_text", ["pay", "exchange", "view-balance", "onboard-kyc"])
def test_high_risk_intents_are_held_not_dispatched(enabled, intent_text):
    """Payments / FX / Wallet / KYC are all high-risk — every one is held, never dispatched."""
    resp = client.post("/v1/intent", json={"intent_text": intent_text})
    assert resp.status_code == 200
    assert resp.json()["disposition"] == "CANARY_HELD"


def test_non_staging_holds_even_when_enabled(monkeypatch):
    """Prod-shaped env: flag ON + a permissive allow-list, but BANXE_ENV != staging →
    the effective allow-list is empty, so even Notifications is held dark (no dispatch)."""
    monkeypatch.setenv("INTENT_LAYER_ENABLED", "true")
    monkeypatch.setenv("BANXE_ENV", "production")
    monkeypatch.setenv("INTENT_LAYER_CANARY_CAPABILITIES", _STAGING_CANARY_CAPS)
    resp = client.post(
        "/v1/intent", json={"intent_text": "notifications", "correlation_id": "c-prod-1"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is True
    assert body["disposition"] == "CANARY_HELD"
    assert body["decision_record"] is None
    assert client.get("/v1/intent/decision/c-prod-1").status_code == 404


def test_get_decision_missing_returns_404(enabled):
    assert client.get("/v1/intent/decision/does-not-exist").status_code == 404


def test_empty_intent_text_is_rejected(enabled):
    assert client.post("/v1/intent", json={"intent_text": ""}).status_code == 422
