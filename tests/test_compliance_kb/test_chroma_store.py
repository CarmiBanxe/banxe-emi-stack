"""
tests/test_compliance_kb/test_chroma_store.py — ChromaDB store tests
IL-CKS-01 | banxe-emi-stack

Uses InMemoryChromaStore (no ChromaDB installation required).
Tests: 8 scenarios covering add, query, delete, count, filter, cosine similarity.
"""

from __future__ import annotations

import pytest

from services.compliance_kb.storage.chroma_store import (
    InMemoryChromaStore,
    _cosine_similarity,
    make_chunk_id,
)
from services.compliance_kb.storage.models import DocumentChunk

COLLECTION = "emi-uk-fca"


def _make_chunk(doc_id: str, idx: int, section: str = "Main", text: str = "text") -> DocumentChunk:
    return DocumentChunk(
        chunk_id=make_chunk_id(doc_id, idx),
        document_id=doc_id,
        section=section,
        text=text,
        char_start=0,
        char_end=len(text),
        metadata={"jurisdiction": "uk", "version": "2024"},
    )


def _unit_vec(dim: int, hot_index: int) -> list[float]:
    """Unit vector with a single 1.0 at hot_index."""
    v = [0.0] * dim
    v[hot_index % dim] = 1.0
    return v


class TestInMemoryChromaStore:
    def test_add_and_count(self):
        """add_chunks increments chunk count."""
        store = InMemoryChromaStore()
        chunks = [_make_chunk("doc-1", i) for i in range(5)]
        embeddings = [_unit_vec(4, i) for i in range(5)]
        store.add_chunks(COLLECTION, chunks, embeddings)
        assert store.get_chunk_count(COLLECTION) == 5

    def test_query_returns_sorted_results(self):
        """query returns results sorted by descending similarity score."""
        store = InMemoryChromaStore()
        # chunk 0 aligns perfectly with query at dim 0
        chunks = [_make_chunk("doc-1", i, text=f"chunk {i}") for i in range(3)]
        embeddings = [_unit_vec(4, i) for i in range(3)]
        store.add_chunks(COLLECTION, chunks, embeddings)

        # Query vector aligns with chunk 0
        query_vec = _unit_vec(4, 0)
        results = store.query(COLLECTION, query_vec, n_results=3)
        assert len(results) == 3
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)
        assert results[0].score == pytest.approx(1.0)

    def test_query_respects_n_results(self):
        """query returns at most n_results items."""
        store = InMemoryChromaStore()
        chunks = [_make_chunk("doc-1", i) for i in range(10)]
        embeddings = [[1.0, 0.0, 0.0, 0.0]] * 10
        store.add_chunks(COLLECTION, chunks, embeddings)
        results = store.query(COLLECTION, [1.0, 0.0, 0.0, 0.0], n_results=5)
        assert len(results) <= 5

    def test_query_with_metadata_filter(self):
        """query respects where-filter on metadata."""
        store = InMemoryChromaStore()
        chunk_uk = _make_chunk("doc-uk", 0, text="UK chunk")
        chunk_uk.metadata["region"] = "uk"
        chunk_eu = _make_chunk("doc-eu", 0, text="EU chunk")
        chunk_eu.metadata["region"] = "eu"

        embedding = [1.0, 0.0, 0.0, 0.0]
        store.add_chunks(COLLECTION, [chunk_uk, chunk_eu], [embedding, embedding])

        results = store.query(COLLECTION, embedding, where={"region": "uk"})
        assert all(r.document_id == "doc-uk" for r in results)

    def test_delete_document_removes_chunks(self):
        """delete_document removes all chunks for a document."""
        store = InMemoryChromaStore()
        chunks_a = [_make_chunk("doc-a", i) for i in range(3)]
        chunks_b = [_make_chunk("doc-b", i) for i in range(2)]
        emb = [1.0, 0.0, 0.0, 0.0]
        store.add_chunks(COLLECTION, chunks_a + chunks_b, [emb] * 5)
        assert store.get_chunk_count(COLLECTION) == 5

        store.delete_document(COLLECTION, "doc-a")
        assert store.get_chunk_count(COLLECTION) == 2
        results = store.query(COLLECTION, emb, n_results=10)
        assert all(r.document_id == "doc-b" for r in results)

    def test_empty_collection_returns_zero_count(self):
        """New collection has count 0."""
        store = InMemoryChromaStore()
        assert store.get_chunk_count("new-collection") == 0

    def test_list_collections(self):
        """list_collections returns collections after add."""
        store = InMemoryChromaStore()
        chunks = [_make_chunk("doc-1", 0)]
        store.add_chunks("col-a", chunks, [[1.0, 0.0]])
        store.add_chunks("col-b", chunks, [[0.0, 1.0]])
        cols = store.list_collections()
        assert "col-a" in cols
        assert "col-b" in cols

    def test_query_empty_collection_returns_empty(self):
        """Querying an empty collection returns no results."""
        store = InMemoryChromaStore()
        results = store.query("empty-col", [1.0, 0.0], n_results=5)
        assert results == []


class TestCosineSimilarity:
    def test_identical_unit_vectors_score_1(self):
        a = [1.0, 0.0, 0.0]
        assert _cosine_similarity(a, a) == pytest.approx(1.0)

    def test_orthogonal_vectors_score_0(self):
        assert _cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_zero_vector_returns_0(self):
        assert _cosine_similarity([0.0, 0.0], [1.0, 0.0]) == pytest.approx(0.0)

    def test_dimension_mismatch_returns_0(self):
        assert _cosine_similarity([1.0, 0.0], [1.0, 0.0, 0.0]) == pytest.approx(0.0)

    def test_parallel_non_unit_vectors(self):
        assert _cosine_similarity([2.0, 0.0], [3.0, 0.0]) == pytest.approx(1.0)


class TestMakeChunkId:
    def test_chunk_id_format(self):
        cid = make_chunk_id("eba-gl-001", 42)
        assert cid == "eba-gl-001::chunk-0042"

    def test_chunk_ids_unique_across_indices(self):
        ids = [make_chunk_id("doc", i) for i in range(100)]
        assert len(set(ids)) == 100
