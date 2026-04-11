"""
services/compliance_kb/embeddings/embedding_service.py — Embedding service
IL-CKS-01 | banxe-emi-stack

Protocol + sentence-transformers implementation + InMemory stub for tests.
Model: all-MiniLM-L6-v2 (384-dim, free/OSS, CPU-compatible).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from services.compliance_kb.constants import EMBEDDING_DIM, EMBEDDING_MODEL

# ── Protocol ───────────────────────────────────────────────────────────────


@runtime_checkable
class EmbeddingServiceProtocol(Protocol):
    """Embedding interface — swappable between sentence-transformers and stubs."""

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts. Returns list of float vectors."""
        ...

    def embed_single(self, text: str) -> list[float]:
        """Embed a single text. Returns a float vector."""
        ...

    @property
    def dimension(self) -> int:
        """Embedding vector dimension."""
        ...


# ── InMemory stub (for unit tests) ─────────────────────────────────────────


class InMemoryEmbeddingService:
    """Deterministic zero-vector stub for unit tests.

    Returns all-zeros vectors (no model loaded — no external dependency).
    Cosine similarity between zero vectors is 0.0 (handled gracefully
    in _cosine_similarity via the norm-zero guard).
    """

    @property
    def dimension(self) -> int:
        return EMBEDDING_DIM

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * EMBEDDING_DIM for _ in texts]

    def embed_single(self, text: str) -> list[float]:
        return [0.0] * EMBEDDING_DIM


# ── Fixed-vector stub (for similarity tests) ───────────────────────────────


class FixedEmbeddingService:
    """Returns a deterministic unit vector for each unique text.

    Useful for tests that need non-zero similarity scores.
    Identical texts always get the same vector.
    """

    def __init__(self) -> None:
        self._cache: dict[str, list[float]] = {}
        self._counter = 0

    @property
    def dimension(self) -> int:
        return EMBEDDING_DIM

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_single(t) for t in texts]

    def embed_single(self, text: str) -> list[float]:
        if text not in self._cache:
            self._counter += 1
            # Create a unit vector with a single non-zero component
            vec = [0.0] * EMBEDDING_DIM
            idx = self._counter % EMBEDDING_DIM
            vec[idx] = 1.0
            self._cache[text] = vec
        return list(self._cache[text])


# ── Production: sentence-transformers ─────────────────────────────────────


class SentenceTransformerEmbeddingService:
    """Production embedding service using sentence-transformers.

    Lazy-loads the model to avoid startup cost when not needed.
    CPU-compatible (GPU optional for speed).
    """

    def __init__(self, model_name: str = EMBEDDING_MODEL) -> None:
        self._model_name = model_name
        self._model: Any = None  # sentence_transformers.SentenceTransformer

    def _get_model(self) -> Any:
        if self._model is None:
            from sentence_transformers import SentenceTransformer  # deferred

            self._model = SentenceTransformer(self._model_name)
        return self._model

    @property
    def dimension(self) -> int:
        return EMBEDDING_DIM

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        model = self._get_model()
        vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return [v.tolist() for v in vectors]

    def embed_single(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]


# ── Factory ────────────────────────────────────────────────────────────────


def make_embedding_service(model_name: str = EMBEDDING_MODEL) -> EmbeddingServiceProtocol:
    """Return the production embedding service (sentence-transformers).

    Use InMemoryEmbeddingService or FixedEmbeddingService in tests.
    """
    return SentenceTransformerEmbeddingService(model_name)
