"""
tests/test_compliance_kb/test_api_routes.py — API route tests for Compliance KB
IL-CKS-01 | banxe-emi-stack

Uses FastAPI TestClient with InMemory stubs for KB service.
Tests: 8 scenarios covering health, list, get, query, search, compare, citation, ingest.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.routers.compliance_kb import get_service
from services.compliance_kb.embeddings.embedding_service import FixedEmbeddingService
from services.compliance_kb.kb_service import ComplianceKBService
from services.compliance_kb.storage.chroma_store import InMemoryChromaStore
from services.compliance_kb.storage.models import Jurisdiction, SourceType


def _make_test_service() -> ComplianceKBService:
    """Build a KB service with InMemory stubs and a pre-loaded notebook."""
    store = InMemoryChromaStore()
    embedder = FixedEmbeddingService()
    # Build service without any YAML (empty notebooks)
    svc = ComplianceKBService(store=store, embedding_service=embedder, config_path="/nonexistent")

    # Manually add test notebooks
    from services.compliance_kb.storage.models import NotebookMetadata, NotebookSource

    svc._notebooks["test-notebook"] = NotebookMetadata(
        id="test-notebook",
        name="Test Notebook",
        description="Used in tests",
        tags=["test", "aml"],
        jurisdiction=Jurisdiction.UK,
        sources=[
            NotebookSource(
                id="test-src-001",
                name="Test Regulation",
                source_type=SourceType.REGULATION,
                url="https://example.com",
                version="2024-01-01",
            )
        ],
        doc_count=0,
    )
    return svc


@pytest.fixture()
def client():
    """TestClient with KB service stub injected."""
    test_svc = _make_test_service()
    app.dependency_overrides[get_service] = lambda: test_svc
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_service, None)


class TestKBHealth:
    def test_health_returns_200(self, client):
        """GET /v1/kb/health returns 200 with status ok."""
        r = client.get("/v1/kb/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert "notebooks" in data


class TestListNotebooks:
    def test_list_returns_notebooks(self, client):
        """GET /v1/kb/notebooks returns notebook list."""
        r = client.get("/v1/kb/notebooks")
        assert r.status_code == 200
        notebooks = r.json()
        assert isinstance(notebooks, list)
        ids = [nb["id"] for nb in notebooks]
        assert "test-notebook" in ids

    def test_list_filter_by_tag(self, client):
        """GET /v1/kb/notebooks?tags=aml returns matching notebooks."""
        r = client.get("/v1/kb/notebooks?tags=aml")
        assert r.status_code == 200
        notebooks = r.json()
        assert any("test-notebook" == nb["id"] for nb in notebooks)

    def test_list_filter_by_jurisdiction(self, client):
        """GET /v1/kb/notebooks?jurisdiction=uk filters correctly."""
        r = client.get("/v1/kb/notebooks?jurisdiction=uk")
        assert r.status_code == 200
        notebooks = r.json()
        assert any(nb["id"] == "test-notebook" for nb in notebooks)


class TestGetNotebook:
    def test_get_existing_notebook(self, client):
        """GET /v1/kb/notebooks/{id} returns full notebook details."""
        r = client.get("/v1/kb/notebooks/test-notebook")
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == "test-notebook"
        assert "sources" in data
        assert len(data["sources"]) == 1

    def test_get_nonexistent_notebook_404(self, client):
        """GET /v1/kb/notebooks/missing returns 404."""
        r = client.get("/v1/kb/notebooks/missing-notebook")
        assert r.status_code == 404


class TestKBQuery:
    def test_query_empty_notebook_returns_answer(self, client):
        """POST /v1/kb/query returns answer even with empty KB."""
        r = client.post(
            "/v1/kb/query",
            json={"notebook_id": "test-notebook", "question": "What is AML?"},
        )
        assert r.status_code == 200
        data = r.json()
        assert "question" in data
        assert "answer" in data
        assert "citations" in data
        assert "notebook_id" in data

    def test_query_missing_notebook_404(self, client):
        """POST /v1/kb/query for missing notebook returns 404."""
        r = client.post(
            "/v1/kb/query",
            json={"notebook_id": "no-such-notebook", "question": "test"},
        )
        assert r.status_code == 404

    def test_query_with_ingested_content(self, client):
        """POST /v1/kb/query after ingestion returns relevant answer."""
        # Ingest some content first
        client.post(
            "/v1/kb/ingest",
            json={
                "notebook_id": "test-notebook",
                "document_id": "test-src-001",
                "name": "Test Regulation",
                "source_type": "regulation",
                "jurisdiction": "uk",
                "version": "2024-01-01",
                "content": (
                    "EMIs must safeguard client funds in segregated accounts. "
                    "Daily reconciliation is required under CASS 7.15. "
                    "Discrepancies must be reported to the FCA within 10 business days."
                ),
            },
        )
        r = client.post(
            "/v1/kb/query",
            json={"notebook_id": "test-notebook", "question": "What is safeguarding?"},
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data["answer"]) > 0


class TestKBSearch:
    def test_search_returns_list(self, client):
        """POST /v1/kb/search returns a list of search results."""
        r = client.post(
            "/v1/kb/search",
            json={"notebook_id": "test-notebook", "query": "AML controls"},
        )
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_search_missing_notebook_404(self, client):
        """POST /v1/kb/search for missing notebook returns 404."""
        r = client.post(
            "/v1/kb/search",
            json={"notebook_id": "missing", "query": "test"},
        )
        assert r.status_code == 404


class TestVersionCompare:
    def test_compare_returns_diff_structure(self, client):
        """POST /v1/kb/compare returns structured diff."""
        r = client.post(
            "/v1/kb/compare",
            json={
                "source_id": "test-src-001",
                "from_version": "2021-01-01",
                "to_version": "2024-01-01",
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert "source_id" in data
        assert "from_version" in data
        assert "to_version" in data
        assert "diff_summary" in data
        assert "changes" in data


class TestGetCitation:
    def test_get_citation_returns_details(self, client):
        """GET /v1/kb/citations/{id} returns citation metadata."""
        r = client.get("/v1/kb/citations/test-src-001?notebook_id=test-notebook")
        assert r.status_code == 200
        data = r.json()
        assert data["source_id"] == "test-src-001"
        assert data["title"] == "Test Regulation"
        assert data["version"] == "2024-01-01"

    def test_get_citation_missing_source_404(self, client):
        """GET /v1/kb/citations/{id} for missing source returns 404."""
        r = client.get("/v1/kb/citations/nonexistent?notebook_id=test-notebook")
        assert r.status_code == 404


class TestIngest:
    def test_ingest_text_content(self, client):
        """POST /v1/kb/ingest with text content returns ok."""
        r = client.post(
            "/v1/kb/ingest",
            json={
                "notebook_id": "test-notebook",
                "document_id": "doc-ingest-001",
                "name": "Test Regulation",
                "source_type": "regulation",
                "jurisdiction": "uk",
                "version": "2024-01-01",
                "content": "This is a regulation about client money safeguarding. " * 10,
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert data["chunks_created"] > 0

    def test_ingest_missing_notebook_404(self, client):
        """POST /v1/kb/ingest into missing notebook returns 404 detail."""
        r = client.post(
            "/v1/kb/ingest",
            json={
                "notebook_id": "no-such-notebook",
                "document_id": "doc-001",
                "name": "Doc",
                "source_type": "regulation",
                "jurisdiction": "uk",
                "version": "2024",
                "content": "some text",
            },
        )
        assert r.status_code == 400  # ValueError maps to 400

    def test_ingest_empty_content_returns_no_content(self, client):
        """POST /v1/kb/ingest with blank content returns no_content status."""
        r = client.post(
            "/v1/kb/ingest",
            json={
                "notebook_id": "test-notebook",
                "document_id": "doc-empty",
                "name": "Empty Doc",
                "source_type": "sop",
                "jurisdiction": "uk",
                "version": "2024",
                "content": "   ",
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "no_content"
        assert data["chunks_created"] == 0
