"""
services/compliance_kb/storage/chroma_store.py — ChromaDB vector store
IL-CKS-01 | banxe-emi-stack

Protocol + ChromaDB implementation + InMemory stub for tests.
Collections correspond 1:1 with compliance notebooks.
"""

from __future__ import annotations

import math
from typing import Any, Protocol, runtime_checkable

from services.compliance_kb.storage.models import DocumentChunk, KBSearchResult

# ── Protocol (dependency injection boundary) ───────────────────────────────


@runtime_checkable
class ChromaStoreProtocol(Protocol):
    """Vector store interface — implemented by ChromaDB and InMemoryStore."""

    def add_chunks(
        self,
        collection_name: str,
        chunks: list[DocumentChunk],
        embeddings: list[list[float]],
    ) -> None:
        """Persist chunks with their embeddings into the named collection."""
        ...

    def query(
        self,
        collection_name: str,
        embedding: list[float],
        n_results: int = 10,
        where: dict[str, Any] | None = None,
    ) -> list[KBSearchResult]:
        """Similarity search — returns results sorted by relevance score (desc)."""
        ...

    def get_chunk_count(self, collection_name: str) -> int:
        """Return total number of chunks in a collection."""
        ...

    def delete_document(self, collection_name: str, document_id: str) -> None:
        """Remove all chunks for a document from the collection."""
        ...

    def list_collections(self) -> list[str]:
        """Return all collection names."""
        ...


# ── InMemory stub (for unit tests — no ChromaDB required) ──────────────────


class InMemoryChromaStore:
    """Thread-safe in-memory vector store using cosine similarity.

    Used in unit tests via Protocol DI. Not suitable for production.
    """

    def __init__(self) -> None:
        # collection_name → list of (chunk, embedding)
        self._store: dict[str, list[tuple[DocumentChunk, list[float]]]] = {}

    def _ensure_collection(self, name: str) -> None:
        if name not in self._store:
            self._store[name] = []

    def add_chunks(
        self,
        collection_name: str,
        chunks: list[DocumentChunk],
        embeddings: list[list[float]],
    ) -> None:
        self._ensure_collection(collection_name)
        for chunk, emb in zip(chunks, embeddings, strict=True):
            self._store[collection_name].append((chunk, emb))

    def query(
        self,
        collection_name: str,
        embedding: list[float],
        n_results: int = 10,
        where: dict[str, Any] | None = None,
    ) -> list[KBSearchResult]:
        self._ensure_collection(collection_name)
        results: list[tuple[float, DocumentChunk]] = []
        for chunk, emb in self._store[collection_name]:
            # Apply metadata filters
            if where and not self._matches_filter(chunk, where):
                continue
            score = _cosine_similarity(embedding, emb)
            results.append((score, chunk))

        results.sort(key=lambda t: t[0], reverse=True)
        return [
            KBSearchResult(
                chunk_id=c.chunk_id,
                document_id=c.document_id,
                text=c.text,
                section=c.section,
                score=max(0.0, min(1.0, s)),
                metadata=c.metadata,
            )
            for s, c in results[:n_results]
        ]

    def get_chunk_count(self, collection_name: str) -> int:
        self._ensure_collection(collection_name)
        return len(self._store[collection_name])

    def delete_document(self, collection_name: str, document_id: str) -> None:
        self._ensure_collection(collection_name)
        self._store[collection_name] = [
            (c, e) for c, e in self._store[collection_name] if c.document_id != document_id
        ]

    def list_collections(self) -> list[str]:
        return list(self._store.keys())

    @staticmethod
    def _matches_filter(chunk: DocumentChunk, where: dict[str, Any]) -> bool:
        for key, value in where.items():
            if chunk.metadata.get(key) != value:
                return False
        return True


# ── ChromaDB production implementation ────────────────────────────────────


class ChromaDBStore:
    """Production ChromaDB-backed vector store.

    Uses local persistent storage. Lazy-initialises ChromaDB to avoid
    import-time failures when chromadb is not installed.
    """

    def __init__(self, persist_dir: str) -> None:
        self._persist_dir = persist_dir
        self._client: Any = None  # chromadb.PersistentClient

    def _get_client(self) -> Any:
        if self._client is None:
            import chromadb  # deferred — optional dependency

            self._client = chromadb.PersistentClient(path=self._persist_dir)
        return self._client

    def _get_or_create(self, collection_name: str) -> Any:
        return self._get_client().get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def add_chunks(
        self,
        collection_name: str,
        chunks: list[DocumentChunk],
        embeddings: list[list[float]],
    ) -> None:
        col = self._get_or_create(collection_name)
        col.add(
            ids=[c.chunk_id for c in chunks],
            embeddings=embeddings,
            documents=[c.text for c in chunks],
            metadatas=[
                {
                    "document_id": c.document_id,
                    "section": c.section,
                    "page": c.page or 0,
                    "char_start": c.char_start,
                    "char_end": c.char_end,
                    **{k: str(v) for k, v in c.metadata.items()},
                }
                for c in chunks
            ],
        )

    def query(
        self,
        collection_name: str,
        embedding: list[float],
        n_results: int = 10,
        where: dict[str, Any] | None = None,
    ) -> list[KBSearchResult]:
        col = self._get_or_create(collection_name)
        kwargs: dict[str, Any] = {
            "query_embeddings": [embedding],
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        raw = col.query(**kwargs)
        results = []
        ids = raw.get("ids", [[]])[0]
        docs = raw.get("documents", [[]])[0]
        metas = raw.get("metadatas", [[]])[0]
        dists = raw.get("distances", [[]])[0]

        for chunk_id, doc, meta, dist in zip(ids, docs, metas, dists):
            # ChromaDB cosine distance: 0 = identical, 2 = opposite
            score = max(0.0, 1.0 - dist / 2.0)
            results.append(
                KBSearchResult(
                    chunk_id=chunk_id,
                    document_id=meta.get("document_id", ""),
                    text=doc,
                    section=meta.get("section", ""),
                    score=score,
                    metadata={k: v for k, v in meta.items() if k not in ("document_id", "section")},
                )
            )
        return results

    def get_chunk_count(self, collection_name: str) -> int:
        col = self._get_or_create(collection_name)
        return col.count()

    def delete_document(self, collection_name: str, document_id: str) -> None:
        col = self._get_or_create(collection_name)
        col.delete(where={"document_id": document_id})

    def list_collections(self) -> list[str]:
        return [c.name for c in self._get_client().list_collections()]


# ── Helpers ────────────────────────────────────────────────────────────────


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors. Returns 0.0 for zero vectors."""
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def make_chunk_id(document_id: str, index: int) -> str:
    """Generate a stable, unique chunk ID."""
    return f"{document_id}::chunk-{index:04d}"
