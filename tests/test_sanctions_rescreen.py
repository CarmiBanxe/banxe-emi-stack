"""
tests/test_sanctions_rescreen.py — Sanctions re-screen endpoint tests
IL-068 | AML/Compliance block | banxe-emi-stack
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.routers.sanctions_rescreen import clear_job_log, get_job_log

client = TestClient(app)

VALID_TOKEN = "test-internal-token"

_RESCREEN_REQUEST = {
    "reason": "watchman_list_update",
    "list_name": "ofac_sdn",
}


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_TOKEN", VALID_TOKEN)
    monkeypatch.delenv("REDIS_URL", raising=False)  # no Redis in tests
    clear_job_log()
    yield
    clear_job_log()


def _post(payload: dict = _RESCREEN_REQUEST, token: str = VALID_TOKEN) -> object:
    return client.post(
        "/compliance/sanctions/rescreen/high-risk",
        json=payload,
        headers={"X-Internal-Token": token},
    )


class TestSanctionsRescreenSecurity:
    def test_missing_token_returns_401(self):
        resp = client.post(
            "/compliance/sanctions/rescreen/high-risk",
            json=_RESCREEN_REQUEST,
        )
        assert resp.status_code == 401

    def test_wrong_token_returns_401(self):
        resp = _post(token="wrong")
        assert resp.status_code == 401

    def test_valid_token_returns_202(self):
        resp = _post()
        assert resp.status_code == 202


class TestSanctionsRescreenResponse:
    def test_response_has_job_id(self):
        resp = _post()
        assert "job_id" in resp.json()
        assert len(resp.json()["job_id"]) == 36  # UUID

    def test_response_has_queued_at(self):
        resp = _post()
        assert "queued_at" in resp.json()

    def test_response_has_queue_name(self):
        resp = _post()
        assert resp.json()["queue"] == "banxe:sanctions:rescreen:high_risk"

    def test_redis_unavailable_returns_false(self):
        """Without REDIS_URL, redis_available should be False."""
        resp = _post()
        assert resp.json()["redis_available"] is False

    def test_missing_reason_returns_422(self):
        resp = _post(payload={"list_name": "ofac_sdn"})
        assert resp.status_code == 422

    def test_optional_list_name(self):
        resp = _post(payload={"reason": "manual_trigger"})
        assert resp.status_code == 202


class TestSanctionsRescreenJobLog:
    def test_job_logged(self):
        _post()
        log = get_job_log()
        assert len(log) == 1
        assert log[0]["reason"] == "watchman_list_update"
        assert log[0]["list_name"] == "ofac_sdn"
        assert log[0]["type"] == "high_risk_rescreen"

    def test_job_has_job_id(self):
        resp = _post()
        job_id = resp.json()["job_id"]
        log = get_job_log()
        assert log[0]["job_id"] == job_id

    def test_multiple_jobs_logged(self):
        _post()
        _post(payload={"reason": "manual_trigger", "list_name": "hmt"})
        log = get_job_log()
        assert len(log) == 2

    def test_failed_auth_not_logged(self):
        _post(token="wrong")
        log = get_job_log()
        assert len(log) == 0
