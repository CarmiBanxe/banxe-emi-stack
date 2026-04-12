"""
tests/test_design_pipeline/test_api.py
IL-D2C-01 — FastAPI Design Pipeline endpoints tests
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from services.design_pipeline.api import router


@pytest.fixture
def app() -> FastAPI:
    """Minimal FastAPI app with the design pipeline router."""
    test_app = FastAPI()
    test_app.include_router(router)
    return test_app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


class TestGenerateComponentEndpoint:
    def test_generate_component_200(self, client: TestClient) -> None:
        response = client.post(
            "/design/generate-component",
            json={
                "file_id": "file-test-001",
                "component_id": "comp-button-001",
                "framework": "react",
                "run_visual_qa": False,
            },
        )
        assert response.status_code == 200

    def test_generate_component_returns_code(self, client: TestClient) -> None:
        response = client.post(
            "/design/generate-component",
            json={
                "file_id": "file-test-001",
                "component_id": "comp-button-001",
                "framework": "react",
                "run_visual_qa": False,
            },
        )
        data = response.json()
        assert "code" in data
        assert len(data["code"]) > 0

    def test_generate_component_success_flag(self, client: TestClient) -> None:
        response = client.post(
            "/design/generate-component",
            json={
                "file_id": "file-test-001",
                "component_id": "comp-button-001",
                "framework": "react",
                "run_visual_qa": False,
            },
        )
        data = response.json()
        assert data["success"] is True

    def test_generate_component_framework_in_response(self, client: TestClient) -> None:
        response = client.post(
            "/design/generate-component",
            json={
                "file_id": "file-test-001",
                "component_id": "comp-button-001",
                "framework": "vue",
                "run_visual_qa": False,
            },
        )
        data = response.json()
        assert data["framework"] == "vue"

    def test_generate_component_with_qa(self, client: TestClient) -> None:
        response = client.post(
            "/design/generate-component",
            json={
                "file_id": "file-test-001",
                "component_id": "comp-button-001",
                "framework": "react",
                "run_visual_qa": True,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "qa_passed" in data

    def test_generate_component_missing_file_id_422(self, client: TestClient) -> None:
        response = client.post(
            "/design/generate-component",
            json={"component_id": "comp-001", "framework": "react"},
        )
        assert response.status_code == 422

    def test_generate_component_missing_component_id_422(self, client: TestClient) -> None:
        response = client.post(
            "/design/generate-component",
            json={"file_id": "file-001", "framework": "react"},
        )
        assert response.status_code == 422

    def test_generate_component_invalid_framework_422(self, client: TestClient) -> None:
        response = client.post(
            "/design/generate-component",
            json={
                "file_id": "file-001",
                "component_id": "comp-001",
                "framework": "invalid_framework",
            },
        )
        assert response.status_code == 422


class TestGeneratePageEndpoint:
    def test_generate_page_200(self, client: TestClient) -> None:
        response = client.post(
            "/design/generate-page",
            json={
                "file_id": "file-test-001",
                "page_id": "page-test-001",
                "framework": "react",
            },
        )
        assert response.status_code == 200

    def test_generate_page_returns_list(self, client: TestClient) -> None:
        response = client.post(
            "/design/generate-page",
            json={
                "file_id": "file-test-001",
                "page_id": "page-test-001",
                "framework": "react",
            },
        )
        data = response.json()
        assert isinstance(data, list)

    def test_generate_page_not_empty(self, client: TestClient) -> None:
        response = client.post(
            "/design/generate-page",
            json={
                "file_id": "file-test-001",
                "page_id": "page-test-001",
                "framework": "react",
            },
        )
        data = response.json()
        assert len(data) > 0


class TestSyncTokensEndpoint:
    def test_sync_tokens_200(self, client: TestClient, tmp_path) -> None:
        import services.design_pipeline.token_extractor as mod

        tokens_file = tmp_path / "banxe-tokens.json"
        orig = mod._BANXE_TOKENS_FILE
        mod._BANXE_TOKENS_FILE = tokens_file
        try:
            response = client.post(
                "/design/sync-tokens",
                json={"file_id": "file-test-001"},
            )
        finally:
            mod._BANXE_TOKENS_FILE = orig
        assert response.status_code == 200

    def test_sync_tokens_returns_file_id(self, client: TestClient, tmp_path) -> None:
        import services.design_pipeline.token_extractor as mod

        tokens_file = tmp_path / "banxe-tokens.json"
        orig = mod._BANXE_TOKENS_FILE
        mod._BANXE_TOKENS_FILE = tokens_file
        try:
            response = client.post(
                "/design/sync-tokens",
                json={"file_id": "file-test-001"},
            )
        finally:
            mod._BANXE_TOKENS_FILE = orig
        data = response.json()
        assert data["file_id"] == "file-test-001"


class TestVisualCompareEndpoint:
    def test_visual_compare_200(self, client: TestClient) -> None:
        response = client.post(
            "/design/visual-compare",
            json={
                "component_id": "comp-001",
                "rendered_html": "<div>test</div>",
                "reference_svg": "<svg><rect/></svg>",
                "threshold": 0.95,
            },
        )
        assert response.status_code == 200

    def test_visual_compare_returns_similarity(self, client: TestClient) -> None:
        response = client.post(
            "/design/visual-compare",
            json={
                "component_id": "comp-001",
                "rendered_html": "<div>test</div>",
                "reference_svg": "<svg><rect/></svg>",
                "threshold": 0.95,
            },
        )
        data = response.json()
        assert "similarity_score" in data
        assert 0.0 <= data["similarity_score"] <= 1.0

    def test_visual_compare_returns_component_id(self, client: TestClient) -> None:
        response = client.post(
            "/design/visual-compare",
            json={
                "component_id": "my-comp",
                "rendered_html": "<div/>",
                "reference_svg": "<svg/>",
                "threshold": 0.95,
            },
        )
        data = response.json()
        assert data["component_id"] == "my-comp"

    def test_visual_compare_invalid_threshold_422(self, client: TestClient) -> None:
        response = client.post(
            "/design/visual-compare",
            json={
                "component_id": "comp",
                "rendered_html": "<div/>",
                "reference_svg": "<svg/>",
                "threshold": 1.5,  # > 1.0
            },
        )
        assert response.status_code == 422


class TestListComponentsEndpoint:
    def test_list_components_200(self, client: TestClient) -> None:
        response = client.get("/design/components/file-test-001")
        assert response.status_code == 200

    def test_list_components_returns_count(self, client: TestClient) -> None:
        response = client.get("/design/components/file-test-001")
        data = response.json()
        assert "count" in data
        assert data["count"] >= 0

    def test_list_components_has_list(self, client: TestClient) -> None:
        response = client.get("/design/components/file-test-001")
        data = response.json()
        assert "components" in data
        assert isinstance(data["components"], list)

    def test_list_components_entries_have_id(self, client: TestClient) -> None:
        response = client.get("/design/components/file-test-001")
        data = response.json()
        if data["components"]:
            assert "id" in data["components"][0]

    def test_list_components_file_id_in_response(self, client: TestClient) -> None:
        response = client.get("/design/components/file-test-001")
        data = response.json()
        assert data["file_id"] == "file-test-001"


class TestGetTokensEndpoint:
    def test_get_tokens_200(self, client: TestClient) -> None:
        response = client.get("/design/tokens/file-test-001")
        assert response.status_code == 200

    def test_get_tokens_returns_file_id(self, client: TestClient) -> None:
        response = client.get("/design/tokens/file-test-001")
        data = response.json()
        assert data["file_id"] == "file-test-001"

    def test_get_tokens_has_color_count(self, client: TestClient) -> None:
        response = client.get("/design/tokens/file-test-001")
        data = response.json()
        assert "color_count" in data
        assert data["color_count"] >= 0

    def test_get_tokens_style_dictionary_has_color(self, client: TestClient) -> None:
        response = client.get("/design/tokens/file-test-001")
        data = response.json()
        assert "style_dictionary" in data
        sd = data["style_dictionary"]
        assert "color" in sd
