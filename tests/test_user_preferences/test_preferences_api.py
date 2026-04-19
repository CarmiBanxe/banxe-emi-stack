"""
tests/test_user_preferences/test_preferences_api.py
IL-UPS-01 | Phase 39 | banxe-emi-stack — 14 tests
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.user_preferences import router

app = FastAPI()
app.include_router(router, prefix="/v1")
client = TestClient(app)


class TestGetAllPreferences:
    def test_get_all_200(self) -> None:
        r = client.get("/v1/preferences/USR-001")
        assert r.status_code == 200

    def test_get_all_has_preferences(self) -> None:
        r = client.get("/v1/preferences/USR-001")
        data = r.json()
        assert "preferences" in data
        assert "user_id" in data


class TestSetPreference:
    def test_set_preference_200(self) -> None:
        r = client.put(
            "/v1/preferences/u1/DISPLAY/theme",
            json={"value": "LIGHT"},
        )
        assert r.status_code == 200

    def test_set_invalid_category_422(self) -> None:
        r = client.put(
            "/v1/preferences/u1/INVALID/theme",
            json={"value": "LIGHT"},
        )
        assert r.status_code == 422

    def test_set_invalid_key_400(self) -> None:
        r = client.put(
            "/v1/preferences/u1/DISPLAY/nonexistent",
            json={"value": "x"},
        )
        assert r.status_code == 400


class TestResetCategory:
    def test_reset_category_200(self) -> None:
        r = client.post("/v1/preferences/u1/DISPLAY/reset")
        assert r.status_code == 200

    def test_reset_invalid_category_422(self) -> None:
        r = client.post("/v1/preferences/u1/INVALID_CAT/reset")
        assert r.status_code == 422


class TestConsents:
    def test_list_consents_200(self) -> None:
        r = client.get("/v1/preferences/u1/consents")
        assert r.status_code == 200

    def test_grant_consent_200(self) -> None:
        r = client.post(
            "/v1/preferences/u1/consents/grant",
            json={"consent_type": "MARKETING", "ip_address": "1.2.3.4", "channel": "web"},
        )
        assert r.status_code == 200

    def test_withdraw_consent_returns_hitl(self) -> None:
        r = client.post(
            "/v1/preferences/u1/consents/withdraw",
            json={"consent_type": "MARKETING"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["hitl_required"] is True

    def test_withdraw_essential_400(self) -> None:
        r = client.post(
            "/v1/preferences/u1/consents/withdraw",
            json={"consent_type": "ESSENTIAL"},
        )
        assert r.status_code == 400


class TestNotifications:
    def test_list_notifications_200(self) -> None:
        r = client.get("/v1/preferences/u1/notifications")
        assert r.status_code == 200

    def test_set_notification_pref_200(self) -> None:
        r = client.put(
            "/v1/preferences/u1/notifications/EMAIL",
            json={"enabled": False},
        )
        assert r.status_code == 200


class TestDataExport:
    def test_request_export_200(self) -> None:
        r = client.post("/v1/preferences/u1/export", json={"format": "json"})
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "COMPLETED"
        assert "export_hash" in data
