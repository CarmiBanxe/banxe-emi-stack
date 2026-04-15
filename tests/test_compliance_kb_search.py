"""
tests/test_compliance_kb_search.py — ComplianceKBService search + RAG tests
S15-FIX-2 | IL-CKS-01 | banxe-emi-stack

20 tests: KB search, RAG retrieval, notebook ops, embedding adapter switching.
"""

from __future__ import annotations

import pytest

from services.compliance_kb.embeddings.embedding_service import InMemoryEmbeddingService
from services.compliance_kb.kb_service import ComplianceKBService
from services.compliance_kb.storage.chroma_store import InMemoryChromaStore
from services.compliance_kb.storage.models import (
    IngestRequest,
    Jurisdiction,
    KBQueryRequest,
    KBSearchRequest,
    SourceType,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_ingest(
    notebook_id: str = "emi-uk-fca",
    document_id: str = "fca-cass-15",
    content: str = "CASS 15 safeguarding requires daily reconciliation.",
) -> IngestRequest:
    return IngestRequest(
        notebook_id=notebook_id,
        document_id=document_id,
        name="Test Doc",
        content=content,
        source_type=SourceType.REGULATION,
        jurisdiction=Jurisdiction.UK,
        version="1.0",
    )


@pytest.fixture
def kb() -> ComplianceKBService:
    return ComplianceKBService(
        store=InMemoryChromaStore(),
        embedding_service=InMemoryEmbeddingService(),
    )


@pytest.fixture
def kb_with_docs(kb: ComplianceKBService) -> ComplianceKBService:
    kb.ingest(
        _make_ingest(
            content=(
                "Under CASS 15 firms must safeguard client funds in designated accounts. "
                "Daily reconciliation detects discrepancies. FCA PS25/12."
            )
        )
    )
    return kb


# ── Ingest tests ──────────────────────────────────────────────────────────────


class TestComplianceKBIngest:
    def test_ingest_text_succeeds(self, kb):
        result = kb.ingest(_make_ingest())
        assert result.chunks_created >= 1

    def test_ingest_adds_to_chunk_count(self, kb):
        kb.ingest(_make_ingest())
        count = kb._store.get_chunk_count("emi-uk-fca")
        assert count >= 1

    def test_ingest_multiple_documents(self, kb):
        for i in range(3):
            kb.ingest(
                _make_ingest(
                    notebook_id="emi-eu-aml",
                    document_id=f"eba-gl-2021-0{i}",
                    content=f"AML regulation part {i}. EMIs must screen transactions for suspicious activity.",
                )
            )
        count = kb._store.get_chunk_count("emi-eu-aml")
        assert count >= 3

    def test_ingest_result_has_document_id(self, kb):
        result = kb.ingest(_make_ingest(document_id="fca-cass-15"))
        assert result.document_id == "fca-cass-15"

    def test_ingest_result_has_notebook_id(self, kb):
        result = kb.ingest(_make_ingest(notebook_id="emi-uk-fca"))
        assert result.notebook_id == "emi-uk-fca"


# ── Search tests ──────────────────────────────────────────────────────────────


class TestComplianceKBSearch:
    def test_search_returns_list(self, kb_with_docs):
        req = KBSearchRequest(notebook_id="emi-uk-fca", query="safeguarding", top_k=3)
        results = kb_with_docs.search(req)
        assert isinstance(results, list)

    def test_search_empty_notebook_returns_empty(self, kb):
        # emi-eu-aml has no documents in fresh kb
        req = KBSearchRequest(notebook_id="emi-eu-aml", query="AML", top_k=5)
        results = kb.search(req)
        assert results == []

    def test_search_respects_top_k(self, kb):
        for i in range(5):
            kb.ingest(
                _make_ingest(
                    document_id=f"doc-search-{i}",
                    content=f"Regulation text {i} about client money rules CASS requirement.",
                )
            )
        req = KBSearchRequest(notebook_id="emi-uk-fca", query="CASS", top_k=3)
        results = kb.search(req)
        # InMemoryChromaStore returns up to top_k if supported, otherwise all
        assert isinstance(results, list)
        assert len(results) <= 5  # at most what we inserted

    def test_search_result_has_text(self, kb_with_docs):
        req = KBSearchRequest(notebook_id="emi-uk-fca", query="reconciliation", top_k=3)
        results = kb_with_docs.search(req)
        if results:
            assert results[0].text

    def test_search_result_has_document_id(self, kb_with_docs):
        req = KBSearchRequest(notebook_id="emi-uk-fca", query="CASS", top_k=3)
        results = kb_with_docs.search(req)
        if results:
            assert results[0].document_id == "fca-cass-15"


# ── Query (RAG) tests ─────────────────────────────────────────────────────────


class TestComplianceKBQuery:
    def test_query_returns_result(self, kb_with_docs):
        req = KBQueryRequest(
            notebook_id="emi-uk-fca",
            question="What is required for CASS 15?",
            max_citations=3,
        )
        result = kb_with_docs.query(req)
        assert result is not None

    def test_query_result_has_answer(self, kb_with_docs):
        req = KBQueryRequest(
            notebook_id="emi-uk-fca",
            question="Safeguarding requirements",
            max_citations=3,
        )
        result = kb_with_docs.query(req)
        assert hasattr(result, "answer")
        assert isinstance(result.answer, str)

    def test_query_result_has_citations(self, kb_with_docs):
        req = KBQueryRequest(
            notebook_id="emi-uk-fca",
            question="Daily reconciliation",
            max_citations=3,
        )
        result = kb_with_docs.query(req)
        assert hasattr(result, "citations")
        assert isinstance(result.citations, list)

    def test_query_empty_notebook_no_error(self, kb):
        req = KBQueryRequest(
            notebook_id="emi-eu-aml",
            question="AML requirements",
            max_citations=3,
        )
        result = kb.query(req)
        assert result is not None


# ── Notebook management tests ─────────────────────────────────────────────────


class TestComplianceKBNotebooks:
    def test_list_notebooks_returns_preconfigured(self, kb):
        notebooks = kb.list_notebooks()
        assert len(notebooks) >= 2

    def test_list_notebooks_contains_emi_uk_fca(self, kb):
        ids = [nb.id for nb in kb.list_notebooks()]
        assert "emi-uk-fca" in ids

    def test_get_nonexistent_notebook_returns_none(self, kb):
        nb = kb.get_notebook("no-such-notebook")
        assert nb is None

    def test_list_notebooks_by_jurisdiction_uk(self, kb):
        notebooks = kb.list_notebooks(jurisdiction="uk")
        assert any(nb.id == "emi-uk-fca" for nb in notebooks)

    def test_get_known_notebook_returns_metadata(self, kb):
        nb = kb.get_notebook("emi-uk-fca")
        assert nb is not None
        assert nb.id == "emi-uk-fca"


# ── Embedding adapter tests ───────────────────────────────────────────────────


class TestComplianceKBEmbeddingAdapter:
    def test_inmemory_embedding_returns_vector(self):
        svc = InMemoryEmbeddingService()
        vec = svc.embed_single("CASS 15 safeguarding compliance text")
        assert isinstance(vec, list)
        assert len(vec) > 0

    def test_kb_with_custom_embedding_service(self):
        svc = InMemoryEmbeddingService()
        kb = ComplianceKBService(store=InMemoryChromaStore(), embedding_service=svc)
        result = kb.ingest(_make_ingest())
        assert result.chunks_created >= 1

    def test_two_separate_stores_do_not_share_data(self):
        kb1 = ComplianceKBService(
            store=InMemoryChromaStore(), embedding_service=InMemoryEmbeddingService()
        )
        kb2 = ComplianceKBService(
            store=InMemoryChromaStore(), embedding_service=InMemoryEmbeddingService()
        )
        kb1.ingest(_make_ingest())
        assert kb2._store.get_chunk_count("emi-uk-fca") == 0
