"""
tests/test_api_compliance_kb.py — Compliance KB router tests
S13-06-FIX-1 | banxe-emi-stack

Tests for GET/POST /v1/kb/* endpoints (compliance_kb.py 39% → ≥85%).
Mocks ComplianceKBService via app.dependency_overrides.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.testclient import TestClient
import pytest

from api.main import app
from api.routers.compliance_kb import get_service
from services.compliance_kb.storage.models import (
    IngestResult,
    Jurisdiction,
    KBQueryResult,
    KBSearchResult,
    NotebookMetadata,
    NotebookSource,
    SourceType,
    VersionCompareResult,
)

client = TestClient(app)


# ── Helpers ────────────────────────────────────────────────────────────────


def _make_source(src_id: str = "src-001") -> NotebookSource:
    return NotebookSource(
        id=src_id,
        name="MLR 2017",
        source_type=SourceType.REGULATION,
        url="https://legislation.gov.uk/uksi/2017/692",
        version="2017-06-26",
    )


def _make_notebook(nb_id: str = "nb-aml") -> NotebookMetadata:
    return NotebookMetadata(
        id=nb_id,
        name="AML Notebook",
        description="UK AML regulatory guidance",
        tags=["aml", "uk"],
        jurisdiction=Jurisdiction.UK,
        sources=[_make_source()],
        doc_count=3,
    )


# ── Fixture ────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def mock_kb_svc():
    mock = MagicMock()
    mock.list_notebooks.return_value = [_make_notebook()]
    mock.get_notebook.return_value = _make_notebook()
    mock.query.return_value = KBQueryResult(
        question="What are SAR requirements?",
        answer="SARs must be filed within 7 days.",
        citations=[],
        notebook_id="nb-aml",
        confidence=0.9,
    )
    mock.search.return_value = [
        KBSearchResult(
            chunk_id="c1",
            document_id="d1",
            text="SAR filing must occur within...",
            section="§3.1",
            score=0.87,
        )
    ]
    mock.compare_versions.return_value = VersionCompareResult(
        source_id="src-001",
        from_version="2017-06-26",
        to_version="2024-01-01",
        diff_summary="One requirement added.",
        changes=[],
    )
    mock.ingest.return_value = IngestResult(
        document_id="doc-001",
        notebook_id="nb-aml",
        chunks_created=5,
        status="ok",
    )
    app.dependency_overrides[get_service] = lambda: mock
    yield mock
    app.dependency_overrides.pop(get_service, None)


# ── Health ─────────────────────────────────────────────────────────────────


def test_kb_health_returns_200():
    resp = client.get("/v1/kb/health")
    assert resp.status_code == 200


def test_kb_health_response_has_status_ok():
    resp = client.get("/v1/kb/health")
    assert resp.json()["status"] == "ok"


def test_kb_health_response_has_notebook_count():
    resp = client.get("/v1/kb/health")
    assert "notebooks" in resp.json()


# ── List notebooks ─────────────────────────────────────────────────────────


def test_list_notebooks_returns_200():
    resp = client.get("/v1/kb/notebooks")
    assert resp.status_code == 200


def test_list_notebooks_returns_list():
    resp = client.get("/v1/kb/notebooks")
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["id"] == "nb-aml"


def test_list_notebooks_with_tag_and_jurisdiction_filters():
    resp = client.get("/v1/kb/notebooks?tags=aml&jurisdiction=uk")
    assert resp.status_code == 200


def test_list_notebooks_empty(mock_kb_svc):
    mock_kb_svc.list_notebooks.return_value = []
    resp = client.get("/v1/kb/notebooks")
    assert resp.status_code == 200
    assert resp.json() == []


# ── Get notebook ───────────────────────────────────────────────────────────


def test_get_notebook_found_returns_200():
    resp = client.get("/v1/kb/notebooks/nb-aml")
    assert resp.status_code == 200
    assert resp.json()["id"] == "nb-aml"


def test_get_notebook_not_found_returns_404(mock_kb_svc):
    mock_kb_svc.get_notebook.return_value = None
    resp = client.get("/v1/kb/notebooks/no-such-nb")
    assert resp.status_code == 404
    assert "no-such-nb" in resp.json()["detail"]


# ── RAG Query ──────────────────────────────────────────────────────────────


def test_query_returns_200():
    resp = client.post(
        "/v1/kb/query",
        json={"notebook_id": "nb-aml", "question": "What are SAR requirements?"},
    )
    assert resp.status_code == 200
    assert "answer" in resp.json()


def test_query_value_error_returns_404(mock_kb_svc):
    mock_kb_svc.query.side_effect = ValueError("Notebook 'no-nb' not found")
    resp = client.post(
        "/v1/kb/query",
        json={"notebook_id": "no-nb", "question": "SAR?"},
    )
    assert resp.status_code == 404


def test_query_generic_exception_returns_500(mock_kb_svc):
    mock_kb_svc.query.side_effect = Exception("vector store unavailable")
    resp = client.post(
        "/v1/kb/query",
        json={"notebook_id": "nb-aml", "question": "SAR?"},
    )
    assert resp.status_code == 500


# ── Search ─────────────────────────────────────────────────────────────────


def test_search_returns_200():
    resp = client.post(
        "/v1/kb/search",
        json={"notebook_id": "nb-aml", "query": "SAR filing"},
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_search_value_error_returns_404(mock_kb_svc):
    mock_kb_svc.search.side_effect = ValueError("Notebook not found")
    resp = client.post(
        "/v1/kb/search",
        json={"notebook_id": "no-nb", "query": "SAR"},
    )
    assert resp.status_code == 404


def test_search_generic_exception_returns_500(mock_kb_svc):
    mock_kb_svc.search.side_effect = Exception("ChromaDB down")
    resp = client.post(
        "/v1/kb/search",
        json={"notebook_id": "nb-aml", "query": "SAR"},
    )
    assert resp.status_code == 500


# ── Compare ────────────────────────────────────────────────────────────────


def test_compare_returns_200():
    resp = client.post(
        "/v1/kb/compare",
        json={
            "source_id": "src-001",
            "from_version": "2017-06-26",
            "to_version": "2024-01-01",
        },
    )
    assert resp.status_code == 200


def test_compare_value_error_returns_400(mock_kb_svc):
    mock_kb_svc.compare_versions.side_effect = ValueError("Version '1999' not found")
    resp = client.post(
        "/v1/kb/compare",
        json={"source_id": "src-001", "from_version": "1999", "to_version": "v2"},
    )
    assert resp.status_code == 400


def test_compare_generic_exception_returns_500(mock_kb_svc):
    mock_kb_svc.compare_versions.side_effect = Exception("diff engine exploded")
    resp = client.post(
        "/v1/kb/compare",
        json={"source_id": "src-001", "from_version": "v1", "to_version": "v2"},
    )
    assert resp.status_code == 500


# ── Citations ──────────────────────────────────────────────────────────────


def test_citations_source_found_returns_200():
    resp = client.get("/v1/kb/citations/src-001?notebook_id=nb-aml")
    assert resp.status_code == 200
    data = resp.json()
    assert data["source_id"] == "src-001"
    assert data["title"] == "MLR 2017"


def test_citations_notebook_not_found_returns_404(mock_kb_svc):
    mock_kb_svc.get_notebook.return_value = None
    resp = client.get("/v1/kb/citations/src-001?notebook_id=no-nb")
    assert resp.status_code == 404
    assert "no-nb" in resp.json()["detail"]


def test_citations_source_not_found_in_notebook_returns_404():
    resp = client.get("/v1/kb/citations/no-such-src?notebook_id=nb-aml")
    assert resp.status_code == 404
    assert "no-such-src" in resp.json()["detail"]


# ── Ingest ─────────────────────────────────────────────────────────────────


def test_ingest_returns_200():
    resp = client.post(
        "/v1/kb/ingest",
        json={
            "notebook_id": "nb-aml",
            "document_id": "doc-001",
            "name": "MLR 2017",
            "source_type": "regulation",
            "jurisdiction": "uk",
            "version": "2017-06-26",
            "content": "SAR must be filed within 7 days of suspicion.",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["chunks_created"] == 5


def test_ingest_file_not_found_returns_404(mock_kb_svc):
    mock_kb_svc.ingest.side_effect = FileNotFoundError("/missing/file.pdf not found")
    resp = client.post(
        "/v1/kb/ingest",
        json={
            "notebook_id": "nb-aml",
            "document_id": "doc-missing",
            "name": "Missing Doc",
            "source_type": "regulation",
            "jurisdiction": "uk",
            "version": "2024-01-01",
            "file_path": "/missing/file.pdf",
        },
    )
    assert resp.status_code == 404


def test_ingest_value_error_returns_400(mock_kb_svc):
    mock_kb_svc.ingest.side_effect = ValueError("content or file_path required")
    resp = client.post(
        "/v1/kb/ingest",
        json={
            "notebook_id": "nb-aml",
            "document_id": "doc-bad",
            "name": "Bad Doc",
            "source_type": "regulation",
            "jurisdiction": "uk",
            "version": "2024-01-01",
        },
    )
    assert resp.status_code == 400


def test_ingest_generic_exception_returns_500(mock_kb_svc):
    mock_kb_svc.ingest.side_effect = Exception("ChromaDB write failed")
    resp = client.post(
        "/v1/kb/ingest",
        json={
            "notebook_id": "nb-aml",
            "document_id": "doc-err",
            "name": "Error Doc",
            "source_type": "regulation",
            "jurisdiction": "uk",
            "version": "2024-01-01",
            "content": "Some text.",
        },
    )
    assert resp.status_code == 500
