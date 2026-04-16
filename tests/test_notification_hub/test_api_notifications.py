"""
tests/test_notification_hub/test_api_notifications.py
IL-NHB-01 | Phase 18 — Notification Hub API endpoint tests

Uses a standalone FastAPI test app (not api.main) to avoid conflicts with the
legacy /v1/notifications router. The router under test is notifications_hub.router.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

import api.routers.notifications_hub as hub_module
from services.notification_hub.channel_dispatcher import ChannelDispatcher
from services.notification_hub.delivery_tracker import DeliveryTracker
from services.notification_hub.models import (
    InMemoryDeliveryStore,
    InMemoryPreferenceStore,
    InMemoryTemplateStore,
)
from services.notification_hub.notification_agent import NotificationAgent
from services.notification_hub.preference_manager import PreferenceManager
from services.notification_hub.template_engine import TemplateEngine

# ─── Standalone test app ──────────────────────────────────────────────────────

_test_app = FastAPI()
_test_app.include_router(hub_module.router, prefix="/v1")


# ─── Agent factory (fresh per-test to avoid lru_cache state leakage) ─────────


def _fresh_agent() -> NotificationAgent:
    template_store = InMemoryTemplateStore()
    preference_store = InMemoryPreferenceStore()
    delivery_store = InMemoryDeliveryStore()
    engine = TemplateEngine(store=template_store)
    adapters = ChannelDispatcher.make_default_adapters(should_succeed=True)
    dispatcher = ChannelDispatcher(adapters=adapters, delivery_store=delivery_store)
    preferences = PreferenceManager(store=preference_store)
    tracker = DeliveryTracker(store=delivery_store, dispatcher=dispatcher, base_delay_secs=0.0)
    return NotificationAgent(
        engine=engine,
        dispatcher=dispatcher,
        preferences=preferences,
        tracker=tracker,
    )


@pytest.fixture(autouse=True)
def patch_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace cached agent with a fresh one for every test."""
    agent = _fresh_agent()
    monkeypatch.setattr(hub_module, "_get_agent", lambda: agent)


client = TestClient(_test_app)

# ─── POST /v1/notifications-hub/send ─────────────────────────────────────────────


def test_send_notification_200() -> None:
    resp = client.post(
        "/v1/notifications-hub/send",
        json={
            "entity_id": "entity-api-001",
            "category": "OPERATIONAL",
            "channel": "EMAIL",
            "template_id": "tmpl-kyc-approved",
            "context": {"name": "Alice"},
            "actor": "system",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data


def test_send_notification_opted_out_returns_opt_out() -> None:
    resp = client.post(
        "/v1/notifications-hub/send",
        json={
            "entity_id": "entity-api-002",
            "category": "PAYMENT",  # default opt-out
            "channel": "EMAIL",
            "template_id": "tmpl-payment-confirmed",
            "context": {},
            "actor": "system",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "OPT_OUT"


def test_send_security_category_default_opt_in() -> None:
    resp = client.post(
        "/v1/notifications-hub/send",
        json={
            "entity_id": "entity-api-003",
            "category": "SECURITY",
            "channel": "SMS",
            "template_id": "tmpl-security-alert",
            "context": {"message": "Test alert"},
            "actor": "system",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "SENT"


def test_send_missing_template_returns_422() -> None:
    resp = client.post(
        "/v1/notifications-hub/send",
        json={
            "entity_id": "entity-api-001",
            "category": "OPERATIONAL",
            "channel": "EMAIL",
            "template_id": "non-existent-template",
            "context": {},
            "actor": "system",
        },
    )
    assert resp.status_code == 422


def test_send_invalid_channel_returns_422() -> None:
    resp = client.post(
        "/v1/notifications-hub/send",
        json={
            "entity_id": "entity-api-001",
            "category": "OPERATIONAL",
            "channel": "PIGEON",
            "template_id": "tmpl-kyc-approved",
            "context": {},
            "actor": "system",
        },
    )
    assert resp.status_code == 422


# ─── POST /v1/notifications-hub/send-bulk ────────────────────────────────────────


def test_send_bulk_returns_list() -> None:
    resp = client.post(
        "/v1/notifications-hub/send-bulk",
        json={
            "entity_ids": ["e-001", "e-002"],
            "category": "OPERATIONAL",
            "channel": "EMAIL",
            "template_id": "tmpl-kyc-approved",
            "context": {"name": "User"},
            "actor": "system",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 2


def test_send_bulk_three_entities_returns_three_results() -> None:
    resp = client.post(
        "/v1/notifications-hub/send-bulk",
        json={
            "entity_ids": ["ea-001", "ea-002", "ea-003"],
            "category": "SECURITY",
            "channel": "SMS",
            "template_id": "tmpl-security-alert",
            "context": {"message": "Alert"},
            "actor": "system",
        },
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 3


# ─── GET /v1/notifications-hub/templates ─────────────────────────────────────────


def test_list_templates_returns_200() -> None:
    resp = client.get("/v1/notifications-hub/templates")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 3


def test_list_templates_filter_by_category_payment() -> None:
    resp = client.get("/v1/notifications-hub/templates?category=PAYMENT")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert all(t["category"] == "PAYMENT" for t in data)


# ─── GET/POST /v1/notifications-hub/preferences/{id} ─────────────────────────────


def test_get_preferences_returns_200() -> None:
    resp = client.get("/v1/notifications-hub/preferences/entity-001")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_set_preference_returns_200() -> None:
    resp = client.post(
        "/v1/notifications-hub/preferences/entity-001",
        json={"channel": "EMAIL", "category": "PAYMENT", "opt_in": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["opt_in"] is True


def test_set_preference_then_check_is_opted_in() -> None:
    # First opt-out OPERATIONAL
    client.post(
        "/v1/notifications-hub/preferences/entity-pref-check",
        json={"channel": "EMAIL", "category": "OPERATIONAL", "opt_in": False},
    )
    # Then opt back in
    resp = client.post(
        "/v1/notifications-hub/preferences/entity-pref-check",
        json={"channel": "EMAIL", "category": "OPERATIONAL", "opt_in": True},
    )
    assert resp.status_code == 200
    # Now send should succeed
    send_resp = client.post(
        "/v1/notifications-hub/send",
        json={
            "entity_id": "entity-pref-check",
            "category": "OPERATIONAL",
            "channel": "EMAIL",
            "template_id": "tmpl-kyc-approved",
            "context": {"name": "User"},
            "actor": "system",
        },
    )
    assert send_resp.json()["status"] == "SENT"


# ─── GET /v1/notifications-hub/delivery/{id} ─────────────────────────────────────


def test_get_delivery_status_returns_200_after_send() -> None:
    send_resp = client.post(
        "/v1/notifications-hub/send",
        json={
            "entity_id": "entity-del-001",
            "category": "SECURITY",
            "channel": "SMS",
            "template_id": "tmpl-security-alert",
            "context": {"message": "Test"},
            "actor": "system",
        },
    )
    record_id = send_resp.json()["id"]
    resp = client.get(f"/v1/notifications-hub/delivery/{record_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == record_id


def test_get_delivery_status_unknown_returns_404() -> None:
    resp = client.get("/v1/notifications-hub/delivery/totally-unknown-record-id")
    assert resp.status_code == 404


# ─── GET /v1/notifications-hub/history/{entity_id} ───────────────────────────────


def test_get_entity_history_returns_200() -> None:
    resp = client.get("/v1/notifications-hub/history/entity-001")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
