"""
tests/test_audit_trail/test_audit_api.py
IL-AES-01 | Phase 40 | banxe-emi-stack — 16 tests
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.audit_trail import router

app = FastAPI()
app.include_router(router, prefix="/v1")
client = TestClient(app)


class TestLogEvent:
    def test_log_event_200(self) -> None:
        r = client.post(
            "/v1/audit-trail/events",
            json={
                "category": "PAYMENT",
                "severity": "INFO",
                "action": "CREATE",
                "entity_type": "payment",
                "entity_id": "PAY-001",
                "actor_id": "USR-001",
                "details": {"amount": "100.00"},
                "source": "API",
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert "event_id" in data
        assert "chain_hash" in data

    def test_log_event_invalid_category_422(self) -> None:
        r = client.post(
            "/v1/audit-trail/events",
            json={
                "category": "INVALID_CAT",
                "action": "CREATE",
                "entity_type": "x",
                "entity_id": "e-1",
                "actor_id": "u1",
            },
        )
        assert r.status_code == 422


class TestGetEvent:
    def test_get_event_200(self) -> None:
        r = client.post(
            "/v1/audit-trail/events",
            json={
                "category": "AUTH",
                "action": "READ",
                "entity_type": "session",
                "entity_id": "S-001",
                "actor_id": "u1",
            },
        )
        event_id = r.json()["event_id"]
        r2 = client.get(f"/v1/audit-trail/events/{event_id}")
        assert r2.status_code == 200
        assert r2.json()["id"] == event_id

    def test_get_nonexistent_404(self) -> None:
        r = client.get("/v1/audit-trail/events/nonexistent-id")
        assert r.status_code == 404


class TestListEntityEvents:
    def test_list_entity_events_200(self) -> None:
        client.post(
            "/v1/audit-trail/events",
            json={
                "category": "ADMIN",
                "action": "UPDATE",
                "entity_type": "config",
                "entity_id": "LIST-ENTITY-001",
                "actor_id": "admin",
            },
        )
        r = client.get("/v1/audit-trail/entities/LIST-ENTITY-001/events")
        assert r.status_code == 200
        data = r.json()
        assert "events" in data


class TestSearchEvents:
    def test_search_events_200(self) -> None:
        r = client.post("/v1/audit-trail/search", json={})
        assert r.status_code == 200

    def test_search_with_category_filter(self) -> None:
        r = client.post("/v1/audit-trail/search", json={"categories": ["PAYMENT"]})
        assert r.status_code == 200
        data = r.json()
        assert "total" in data

    def test_search_invalid_category_422(self) -> None:
        r = client.post("/v1/audit-trail/search", json={"categories": ["INVALID"]})
        assert r.status_code == 422


class TestReplayEntity:
    def test_replay_entity_200(self) -> None:
        r = client.get(
            "/v1/audit-trail/entities/any-entity/replay",
            params={
                "from_ts": "2024-01-01T00:00:00+00:00",
                "to_ts": "2030-12-31T00:00:00+00:00",
            },
        )
        assert r.status_code == 200

    def test_replay_entity_invalid_ts_422(self) -> None:
        r = client.get(
            "/v1/audit-trail/entities/any-entity/replay",
            params={"from_ts": "not-a-date", "to_ts": "also-not"},
        )
        assert r.status_code == 422


class TestGetEntityState:
    def test_get_state_200(self) -> None:
        r = client.get(
            "/v1/audit-trail/entities/any-entity/state",
            params={"as_of": "2030-12-31T00:00:00+00:00"},
        )
        assert r.status_code == 200

    def test_get_state_invalid_ts_422(self) -> None:
        r = client.get(
            "/v1/audit-trail/entities/any/state",
            params={"as_of": "not-a-date"},
        )
        assert r.status_code == 422


class TestIntegrity:
    def test_verify_integrity_200(self) -> None:
        r = client.get("/v1/audit-trail/integrity/API")
        assert r.status_code == 200
        data = r.json()
        assert "status" in data

    def test_verify_integrity_invalid_422(self) -> None:
        r = client.get("/v1/audit-trail/integrity/INVALID_SOURCE")
        assert r.status_code == 422


class TestRetention:
    def test_list_rules_200(self) -> None:
        r = client.get("/v1/audit-trail/retention/rules")
        assert r.status_code == 200
        data = r.json()
        assert "rules" in data
        assert len(data["rules"]) == 4

    def test_schedule_purge_returns_hitl(self) -> None:
        r = client.post(
            "/v1/audit-trail/retention/purge",
            json={"category": "AML", "older_than_days": 1825},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["hitl_required"] is True

    def test_schedule_purge_invalid_category_422(self) -> None:
        r = client.post(
            "/v1/audit-trail/retention/purge",
            json={"category": "INVALID", "older_than_days": 100},
        )
        assert r.status_code == 422

    def test_append_only_no_delete_endpoint(self) -> None:
        r = client.delete("/v1/audit-trail/events/some-id")
        assert r.status_code == 405
