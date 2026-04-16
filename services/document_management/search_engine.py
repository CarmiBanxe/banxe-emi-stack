"""
services/document_management/search_engine.py — SearchEngine
IL-DMS-01 | Phase 24 | banxe-emi-stack

Document search: keyword-based indexing and querying with optional entity/category filters.
"""

from __future__ import annotations

from services.document_management.models import (
    Document,
    DocumentCategory,
    DocumentSearchResult,
    DocumentStorePort,
    SearchIndexPort,
)


class SearchEngine:
    """Document search engine backed by SearchIndexPort."""

    def __init__(
        self,
        search_index: SearchIndexPort,
        document_store: DocumentStorePort,
    ) -> None:
        self._index = search_index
        self._docs = document_store

    async def index_document(self, doc: Document, content: str = "") -> None:
        """Index a document for search."""
        await self._index.index(doc, content)

    async def search(
        self,
        query: str,
        entity_id: str | None = None,
        category: DocumentCategory | None = None,
    ) -> list[DocumentSearchResult]:
        """
        Search documents by keyword.

        Optionally filter by entity_id and category.
        Returns results sorted by relevance_score descending.
        """
        results = await self._index.search(query, category=category)

        if entity_id is not None:
            filtered: list[DocumentSearchResult] = []
            for result in results:
                doc = await self._docs.get(result.doc_id)
                if doc is not None and doc.entity_id == entity_id:
                    filtered.append(result)
            results = filtered

        return sorted(results, key=lambda r: r.relevance_score, reverse=True)

    async def reindex_all(self, entity_id: str) -> int:
        """Re-index all documents for an entity. Returns count of indexed docs."""
        docs = await self._docs.list_by_entity(entity_id=entity_id, category=None)
        for doc in docs:
            await self._index.index(doc, "")
        return len(docs)
