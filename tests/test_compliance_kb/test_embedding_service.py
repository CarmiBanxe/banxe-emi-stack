"""
tests/test_compliance_kb/test_embedding_service.py — Embedding service tests
IL-CKS-01 | banxe-emi-stack

Uses InMemory and Fixed stubs — no sentence-transformers installed required.
Tests: 4 scenarios covering dimension, batch, single, and Protocol compliance.
"""

from __future__ import annotations

import pytest

from services.compliance_kb.constants import EMBEDDING_DIM
from services.compliance_kb.embeddings.embedding_service import (
    EmbeddingServiceProtocol,
    FixedEmbeddingService,
    InMemoryEmbeddingService,
)


class TestInMemoryEmbeddingService:
    def test_dimension_matches_constant(self):
        svc = InMemoryEmbeddingService()
        assert svc.dimension == EMBEDDING_DIM

    def test_embed_single_returns_correct_length(self):
        svc = InMemoryEmbeddingService()
        vec = svc.embed_single("test text")
        assert len(vec) == EMBEDDING_DIM

    def test_embed_batch_returns_correct_shape(self):
        svc = InMemoryEmbeddingService()
        texts = ["text one", "text two", "text three"]
        vecs = svc.embed_batch(texts)
        assert len(vecs) == 3
        assert all(len(v) == EMBEDDING_DIM for v in vecs)

    def test_embed_returns_zero_vectors(self):
        svc = InMemoryEmbeddingService()
        vec = svc.embed_single("anything")
        assert all(v == 0.0 for v in vec)

    def test_satisfies_protocol(self):
        svc = InMemoryEmbeddingService()
        assert isinstance(svc, EmbeddingServiceProtocol)

    def test_embed_empty_batch(self):
        svc = InMemoryEmbeddingService()
        result = svc.embed_batch([])
        assert result == []


class TestFixedEmbeddingService:
    def test_same_text_same_vector(self):
        svc = FixedEmbeddingService()
        v1 = svc.embed_single("hello compliance")
        v2 = svc.embed_single("hello compliance")
        assert v1 == v2

    def test_different_texts_different_vectors(self):
        svc = FixedEmbeddingService()
        v1 = svc.embed_single("AML requirements")
        v2 = svc.embed_single("FCA safeguarding rules")
        # Different texts should not produce identical vectors
        assert v1 != v2

    def test_vectors_are_unit_length(self):
        import math

        svc = FixedEmbeddingService()
        v = svc.embed_single("test")
        norm = math.sqrt(sum(x * x for x in v))
        assert norm == pytest.approx(1.0, abs=1e-6)

    def test_batch_consistent_with_single(self):
        svc = FixedEmbeddingService()
        texts = ["alpha", "beta", "gamma"]
        batch = svc.embed_batch(texts)
        singles = [svc.embed_single(t) for t in texts]
        assert batch == singles

    def test_satisfies_protocol(self):
        svc = FixedEmbeddingService()
        assert isinstance(svc, EmbeddingServiceProtocol)
