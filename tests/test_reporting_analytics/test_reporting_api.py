"""
tests/test_reporting_analytics/test_reporting_api.py
IL-RAP-01 | Phase 38 | banxe-emi-stack — 15 tests
"""

from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from api.main import app

client = TestClient(app)

# Grab a seeded template id for reuse
_SEEDED_TEMPLATES: list[str] = []


def _get_template_id() -> str:
    if not _SEEDED_TEMPLATES:
        resp = client.get("/v1/reports/templates")
        templates = resp.json()
        if templates:
            _SEEDED_TEMPLATES.append(templates[0]["id"])
    return _SEEDED_TEMPLATES[0] if _SEEDED_TEMPLATES else ""


class TestListTemplates:
    def test_list_templates_200(self) -> None:
        response = client.get("/v1/reports/templates")
        assert response.status_code == 200

    def test_returns_list(self) -> None:
        response = client.get("/v1/reports/templates")
        assert isinstance(response.json(), list)


class TestCreateTemplate:
    def test_create_template_201(self) -> None:
        response = client.post(
            "/v1/reports/templates",
            json={
                "name": "Test Template",
                "report_type": "COMPLIANCE",
                "sources": ["TRANSACTIONS"],
                "format": "JSON",
            },
        )
        assert response.status_code == 201

    def test_invalid_type_400(self) -> None:
        response = client.post(
            "/v1/reports/templates",
            json={
                "name": "Test",
                "report_type": "INVALID_TYPE",
            },
        )
        assert response.status_code == 400


class TestGenerateReport:
    def test_generate_201(self) -> None:
        tid = _get_template_id()
        if not tid:
            pytest.skip("No seeded templates")
        response = client.post(
            "/v1/reports/generate",
            json={
                "template_id": tid,
                "parameters": {},
            },
        )
        assert response.status_code == 201

    def test_invalid_template_400(self) -> None:
        response = client.post(
            "/v1/reports/generate",
            json={
                "template_id": "bad-template-id",
                "parameters": {},
            },
        )
        assert response.status_code == 400

    def test_returns_job_id(self) -> None:
        tid = _get_template_id()
        if not tid:
            pytest.skip("No seeded templates")
        response = client.post(
            "/v1/reports/generate",
            json={
                "template_id": tid,
                "parameters": {},
            },
        )
        data = response.json()
        assert "job_id" in data


class TestGetJob:
    def test_get_job_200(self) -> None:
        tid = _get_template_id()
        if not tid:
            pytest.skip("No seeded templates")
        gen = client.post("/v1/reports/generate", json={"template_id": tid, "parameters": {}})
        job_id = gen.json()["job_id"]
        response = client.get(f"/v1/reports/jobs/{job_id}")
        assert response.status_code == 200

    def test_unknown_job_404(self) -> None:
        response = client.get("/v1/reports/jobs/nonexistent-job-id")
        assert response.status_code == 404


class TestExportReport:
    def test_export_json_200(self) -> None:
        tid = _get_template_id()
        if not tid:
            pytest.skip("No seeded templates")
        gen = client.post("/v1/reports/generate", json={"template_id": tid, "parameters": {}})
        job_id = gen.json()["job_id"]
        response = client.get(f"/v1/reports/jobs/{job_id}/export?format=json")
        assert response.status_code == 200


class TestDashboardKpis:
    def test_get_kpis_200(self) -> None:
        response = client.get("/v1/reports/dashboard/kpis")
        assert response.status_code == 200

    def test_kpi_values_are_strings(self) -> None:
        response = client.get("/v1/reports/dashboard/kpis")
        kpis = response.json()
        for kpi in kpis:
            assert isinstance(kpi["value"], str)


class TestSchedules:
    def test_create_schedule_201(self) -> None:
        tid = _get_template_id()
        if not tid:
            pytest.skip("No seeded templates")
        response = client.post(
            "/v1/reports/schedules",
            json={
                "template_id": tid,
                "frequency": "DAILY",
                "delivery": {"channel": "email"},
                "created_by": "test-user",
            },
        )
        assert response.status_code == 201

    def test_list_schedules_200(self) -> None:
        response = client.get("/v1/reports/schedules")
        assert response.status_code == 200

    def test_update_schedule_returns_hitl(self) -> None:
        tid = _get_template_id()
        if not tid:
            pytest.skip("No seeded templates")
        sched = client.post(
            "/v1/reports/schedules",
            json={
                "template_id": tid,
                "frequency": "DAILY",
            },
        )
        sched_id = sched.json()["id"]
        response = client.post(
            f"/v1/reports/schedules/{sched_id}",
            json={
                "frequency": "WEEKLY",
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "HITL_REQUIRED"
