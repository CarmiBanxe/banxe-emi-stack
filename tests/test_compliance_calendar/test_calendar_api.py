"""
tests/test_compliance_calendar/test_calendar_api.py
IL-CCD-01 | Phase 42 | 17 tests
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


class TestListDeadlines:
    def test_list_200(self) -> None:
        resp = client.get("/v1/compliance-calendar/deadlines")
        assert resp.status_code == 200

    def test_list_has_deadlines(self) -> None:
        resp = client.get("/v1/compliance-calendar/deadlines")
        data = resp.json()
        assert "deadlines" in data
        assert len(data["deadlines"]) >= 5

    def test_list_count_field(self) -> None:
        resp = client.get("/v1/compliance-calendar/deadlines")
        data = resp.json()
        assert "count" in data


class TestCreateDeadline:
    def test_create_200(self) -> None:
        resp = client.post(
            "/v1/compliance-calendar/deadlines",
            json={
                "title": "Test API Deadline",
                "deadline_type": "CUSTOM",
                "priority": "MEDIUM",
                "due_date": "2026-12-31",
                "owner": "tester",
                "description": "API test",
            },
        )
        assert resp.status_code == 200

    def test_create_invalid_type_422(self) -> None:
        resp = client.post(
            "/v1/compliance-calendar/deadlines",
            json={
                "title": "Test",
                "deadline_type": "INVALID",
                "priority": "MEDIUM",
                "due_date": "2026-12-31",
                "owner": "tester",
            },
        )
        assert resp.status_code == 422

    def test_create_returns_status_upcoming(self) -> None:
        resp = client.post(
            "/v1/compliance-calendar/deadlines",
            json={
                "title": "New Deadline",
                "deadline_type": "AUDIT",
                "priority": "HIGH",
                "due_date": "2026-11-30",
                "owner": "CCO",
            },
        )
        data = resp.json()
        assert data["status"] == "UPCOMING"


class TestGetDeadline:
    def test_get_seeded_deadline(self) -> None:
        resp = client.get("/v1/compliance-calendar/deadlines/dl-fca-fin060-q1")
        assert resp.status_code == 200

    def test_get_nonexistent_404(self) -> None:
        resp = client.get("/v1/compliance-calendar/deadlines/nonexistent-id")
        assert resp.status_code == 404


class TestCompleteDeadline:
    def test_complete_existing_200(self) -> None:
        create_resp = client.post(
            "/v1/compliance-calendar/deadlines",
            json={
                "title": "To Complete",
                "deadline_type": "CUSTOM",
                "priority": "LOW",
                "due_date": "2026-12-01",
                "owner": "owner",
            },
        )
        dl_id = create_resp.json()["id"]
        resp = client.post(
            f"/v1/compliance-calendar/deadlines/{dl_id}/complete", json={"evidence": "signed doc"}
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "COMPLETED"

    def test_complete_nonexistent_404(self) -> None:
        resp = client.post(
            "/v1/compliance-calendar/deadlines/bad-id/complete", json={"evidence": "x"}
        )
        assert resp.status_code == 404


class TestGetUpcoming:
    def test_upcoming_200(self) -> None:
        resp = client.get("/v1/compliance-calendar/deadlines/upcoming?days=365")
        assert resp.status_code == 200

    def test_upcoming_has_deadlines(self) -> None:
        resp = client.get("/v1/compliance-calendar/deadlines/upcoming?days=365")
        data = resp.json()
        assert "deadlines" in data


class TestGetOverdue:
    def test_overdue_200(self) -> None:
        resp = client.get("/v1/compliance-calendar/deadlines/overdue")
        assert resp.status_code == 200


class TestCreateTask:
    def test_create_task_200(self) -> None:
        resp = client.post(
            "/v1/compliance-calendar/tasks",
            json={
                "deadline_id": "dl-fca-fin060-q1",
                "title": "Draft filing",
                "assigned_to": "CFO",
            },
        )
        assert resp.status_code == 200

    def test_create_task_status_pending(self) -> None:
        resp = client.post(
            "/v1/compliance-calendar/tasks",
            json={
                "deadline_id": "dl-aml-annual-2026",
                "title": "AML task",
                "assigned_to": "MLRO",
            },
        )
        data = resp.json()
        assert data["status"] == "PENDING"


class TestGetTask:
    def test_get_created_task(self) -> None:
        create_resp = client.post(
            "/v1/compliance-calendar/tasks",
            json={
                "deadline_id": "dl-board-q1-risk",
                "title": "Board task",
                "assigned_to": "CRO",
            },
        )
        task_id = create_resp.json()["id"]
        resp = client.get(f"/v1/compliance-calendar/tasks/{task_id}")
        assert resp.status_code == 200

    def test_get_nonexistent_task_404(self) -> None:
        resp = client.get("/v1/compliance-calendar/tasks/nonexistent-task")
        assert resp.status_code == 404


class TestGetComplianceScore:
    def test_score_200(self) -> None:
        resp = client.get("/v1/compliance-calendar/score")
        assert resp.status_code == 200

    def test_score_is_string(self) -> None:
        resp = client.get("/v1/compliance-calendar/score")
        data = resp.json()
        assert isinstance(data["compliance_score"], str)
