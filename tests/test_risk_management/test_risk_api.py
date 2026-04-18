"""
tests/test_risk_management/test_risk_api.py
IL-RMS-01 | Phase 37 | banxe-emi-stack — 15 tests
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


class TestScoreEntity:
    def test_score_entity_201(self) -> None:
        response = client.post(
            "/v1/risk/score",
            json={
                "entity_id": "e-api-1",
                "category": "AML",
                "factors": {"pep": "10", "geo": "20"},
            },
        )
        assert response.status_code == 201

    def test_score_entity_returns_score(self) -> None:
        response = client.post(
            "/v1/risk/score",
            json={
                "entity_id": "e-api-2",
                "category": "CREDIT",
                "factors": {},
            },
        )
        data = response.json()
        assert "score" in data
        assert "level" in data

    def test_score_entity_score_is_string(self) -> None:
        response = client.post(
            "/v1/risk/score",
            json={
                "entity_id": "e-api-3",
                "category": "FRAUD",
                "factors": {"f": "30"},
            },
        )
        data = response.json()
        assert isinstance(data["score"], str)

    def test_score_entity_invalid_category_400(self) -> None:
        response = client.post(
            "/v1/risk/score",
            json={
                "entity_id": "e-1",
                "category": "NOT_A_CATEGORY",
                "factors": {},
            },
        )
        assert response.status_code == 400


class TestGetEntityScores:
    def test_get_scores_200(self) -> None:
        # First create a score
        client.post(
            "/v1/risk/score",
            json={
                "entity_id": "e-scores-1",
                "category": "AML",
                "factors": {"f": "30"},
            },
        )
        response = client.get("/v1/risk/entities/e-scores-1/scores")
        assert response.status_code == 200

    def test_get_scores_returns_list(self) -> None:
        response = client.get("/v1/risk/entities/nonexistent-entity-xyz/scores")
        assert response.status_code == 200
        assert isinstance(response.json(), list)


class TestGetAssessment:
    def test_get_assessment_200(self) -> None:
        response = client.get("/v1/risk/entities/entity-seed-001/assessment")
        assert response.status_code == 200

    def test_get_assessment_has_aggregate(self) -> None:
        response = client.get("/v1/risk/entities/entity-seed-001/assessment")
        data = response.json()
        assert "aggregate_score" in data


class TestPortfolioHeatmap:
    def test_heatmap_200(self) -> None:
        response = client.post(
            "/v1/risk/portfolio/heatmap",
            json={
                "entity_ids": ["entity-seed-001"],
            },
        )
        assert response.status_code == 200

    def test_heatmap_returns_dict(self) -> None:
        response = client.post(
            "/v1/risk/portfolio/heatmap",
            json={
                "entity_ids": [],
            },
        )
        assert response.status_code == 200
        assert isinstance(response.json(), dict)


class TestConcentration:
    def test_concentration_200(self) -> None:
        response = client.get("/v1/risk/portfolio/concentration")
        assert response.status_code == 200

    def test_concentration_has_distribution(self) -> None:
        response = client.get("/v1/risk/portfolio/concentration")
        data = response.json()
        assert "distribution" in data


class TestThresholds:
    def test_list_thresholds_200(self) -> None:
        response = client.get("/v1/risk/thresholds")
        assert response.status_code == 200

    def test_set_threshold_returns_hitl(self) -> None:
        response = client.post(
            "/v1/risk/thresholds/AML",
            json={
                "low_max": "20",
                "medium_max": "45",
                "high_max": "70",
                "alert_on_breach": True,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "HITL_REQUIRED"

    def test_invalid_threshold_category_400(self) -> None:
        response = client.post(
            "/v1/risk/thresholds/INVALID_CAT",
            json={
                "low_max": "20",
                "medium_max": "45",
                "high_max": "70",
            },
        )
        assert response.status_code == 400


class TestReports:
    def test_generate_report_201(self) -> None:
        response = client.post(
            "/v1/risk/reports",
            json={
                "scope": "global",
                "period_start": "2026-01-01",
                "period_end": "2026-03-31",
            },
        )
        assert response.status_code == 201

    def test_generate_report_has_id(self) -> None:
        response = client.post(
            "/v1/risk/reports",
            json={
                "scope": "test",
                "period_start": "2026-01-01",
                "period_end": "2026-03-31",
            },
        )
        data = response.json()
        assert "id" in data
