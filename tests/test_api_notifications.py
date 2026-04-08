"""
tests/test_api_notifications.py — Notifications API endpoint tests
IL-047 | S17-03 | banxe-emi-stack
"""
import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.routers.notifications import _get_notification_service
from services.notifications.mock_notification_adapter import MockNotificationAdapter
from services.notifications.notification_service import NotificationService

client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh_notification_service():
    """Override with a fresh service for each test."""
    adapter = MockNotificationAdapter()
    svc = NotificationService(adapter=adapter)
    app.dependency_overrides[_get_notification_service] = lambda: svc
    _get_notification_service.cache_clear()
    yield svc, adapter
    app.dependency_overrides.clear()
    _get_notification_service.cache_clear()


_SEND_PAYLOAD = {
    "notification_type": "payment.sent",
    "channel": "EMAIL",
    "recipient_email": "alice@example.com",
    "template_vars": {
        "amount": "100.00",
        "currency": "£",
        "creditor_name": "Bob",
        "rail": "FPS",
        "reference": "REF-001",
    },
    "transactional": True,
}


def test_send_notification_returns_201():
    resp = client.post("/v1/notifications/send", json=_SEND_PAYLOAD)
    assert resp.status_code == 201


def test_send_notification_status_sent():
    resp = client.post("/v1/notifications/send", json=_SEND_PAYLOAD)
    assert resp.json()["status"] == "SENT"


def test_send_notification_has_id():
    resp = client.post("/v1/notifications/send", json=_SEND_PAYLOAD)
    assert "notification_id" in resp.json()
    assert resp.json()["notification_id"]


def test_send_notification_channel():
    resp = client.post("/v1/notifications/send", json=_SEND_PAYLOAD)
    assert resp.json()["channel"] == "EMAIL"


def test_send_notification_type():
    resp = client.post("/v1/notifications/send", json=_SEND_PAYLOAD)
    assert resp.json()["notification_type"] == "payment.sent"


def test_send_notification_no_recipient_returns_422():
    payload = {k: v for k, v in _SEND_PAYLOAD.items() if k != "recipient_email"}
    resp = client.post("/v1/notifications/send", json=payload)
    assert resp.status_code == 422


def test_send_notification_invalid_type_returns_422():
    payload = {**_SEND_PAYLOAD, "notification_type": "not.a.real.type"}
    resp = client.post("/v1/notifications/send", json=payload)
    assert resp.status_code == 422


def test_send_notification_invalid_channel_returns_422():
    payload = {**_SEND_PAYLOAD, "channel": "CARRIER_PIGEON"}
    resp = client.post("/v1/notifications/send", json=payload)
    assert resp.status_code == 422


def test_send_telegram_notification():
    payload = {
        **_SEND_PAYLOAD,
        "channel": "TELEGRAM",
        "recipient_email": None,
        "recipient_telegram_id": "123456789",
    }
    resp = client.post("/v1/notifications/send", json=payload)
    assert resp.status_code == 201
    assert resp.json()["channel"] == "TELEGRAM"


def test_send_kyc_approved_notification():
    payload = {
        "notification_type": "kyc.approved",
        "channel": "EMAIL",
        "recipient_email": "alice@example.com",
        "transactional": True,
    }
    resp = client.post("/v1/notifications/send", json=payload)
    assert resp.status_code == 201
    assert resp.json()["status"] == "SENT"


def test_get_status_returns_200():
    send_resp = client.post("/v1/notifications/send", json=_SEND_PAYLOAD)
    nid = send_resp.json()["notification_id"]
    resp = client.get(f"/v1/notifications/{nid}/status")
    assert resp.status_code == 200


def test_get_status_matches_send():
    send_resp = client.post("/v1/notifications/send", json=_SEND_PAYLOAD)
    nid = send_resp.json()["notification_id"]
    resp = client.get(f"/v1/notifications/{nid}/status")
    assert resp.json()["notification_id"] == nid


def test_get_status_not_found_returns_404():
    resp = client.get("/v1/notifications/nonexistent-id/status")
    assert resp.status_code == 404


def test_preview_endpoint_returns_200():
    resp = client.get(
        "/v1/notifications/preview",
        params={"notification_type": "payment.sent"},
    )
    assert resp.status_code == 200


def test_preview_endpoint_body_not_empty():
    resp = client.get(
        "/v1/notifications/preview",
        params={"notification_type": "payment.sent", "amount": "250.00"},
    )
    assert resp.json()["body"]


def test_preview_endpoint_invalid_type_returns_422():
    resp = client.get(
        "/v1/notifications/preview",
        params={"notification_type": "not.valid"},
    )
    assert resp.status_code == 422


def test_send_safeguarding_shortfall_telegram():
    payload = {
        "notification_type": "safeguarding.shortfall",
        "channel": "TELEGRAM",
        "recipient_telegram_id": "-100987654321",
        "template_vars": {
            "internal_balance": "£100,000",
            "external_balance": "£99,000",
            "delta": "£1,000",
            "recon_date": "2026-04-08",
        },
        "transactional": True,
    }
    resp = client.post("/v1/notifications/send", json=payload)
    assert resp.status_code == 201
