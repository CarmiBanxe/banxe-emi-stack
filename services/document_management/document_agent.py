"""
services/document_management/document_agent.py — DocumentAgent
IL-DMS-01 | Phase 24 | banxe-emi-stack

Orchestrates DocumentStoreService, VersionManager, RetentionEngine,
SearchEngine, and AccessController into a unified document management API.

Document deletion always returns HITL_REQUIRED (I-27): deletion is irreversible
and requires Compliance Officer approval.
"""

from __future__ import annotations

from services.document_management.access_controller import AccessController
from services.document_management.document_store import DocumentStoreService
from services.document_management.models import AccessLevel, DocumentCategory
from services.document_management.retention_engine import RetentionEngine
from services.document_management.search_engine import SearchEngine
from services.document_management.version_manager import VersionManager


class DocumentAgent:
    """Orchestrates all document management components."""

    def __init__(
        self,
        document_store: DocumentStoreService,
        version_manager: VersionManager,
        retention_engine: RetentionEngine,
        search_engine: SearchEngine,
        access_controller: AccessController,
    ) -> None:
        self._store = document_store
        self._versions = version_manager
        self._retention = retention_engine
        self._search = search_engine
        self._access = access_controller

    async def upload_document(
        self,
        name: str,
        category: str,
        content: str,
        entity_id: str,
        uploaded_by: str,
        role: str,
        access_level: str = "INTERNAL",
        tags: list[str] | None = None,
    ) -> dict:
        """Upload a document and index it for search."""
        doc_category = DocumentCategory(category)
        doc_access_level = AccessLevel(access_level)
        doc_tags: tuple[str, ...] = tuple(tags) if tags else ()

        doc = await self._store.upload(
            name=name,
            category=doc_category,
            content=content,
            entity_id=entity_id,
            uploaded_by=uploaded_by,
            access_level=doc_access_level,
            tags=doc_tags,
        )
        await self._search.index_document(doc, content)

        return {
            "doc_id": doc.doc_id,
            "name": doc.name,
            "category": doc.category.value,
            "content_hash": doc.content_hash,
            "size_bytes": doc.size_bytes,
            "status": doc.status.value,
            "access_level": doc.access_level.value,
            "entity_id": doc.entity_id,
            "uploaded_by": doc.uploaded_by,
            "created_at": doc.created_at.isoformat(),
            "tags": list(doc.tags),
        }

    async def get_document(
        self,
        doc_id: str,
        accessed_by: str,
        role: str,
    ) -> dict | None:
        """Retrieve a document if the role has access."""
        allowed = await self._access.check_access(doc_id, role, "VIEW")
        if not allowed:
            return None

        doc = await self._store.get_document(doc_id, accessed_by)
        if doc is None:
            return None

        return {
            "doc_id": doc.doc_id,
            "name": doc.name,
            "category": doc.category.value,
            "content_hash": doc.content_hash,
            "size_bytes": doc.size_bytes,
            "status": doc.status.value,
            "access_level": doc.access_level.value,
            "entity_id": doc.entity_id,
            "uploaded_by": doc.uploaded_by,
            "created_at": doc.created_at.isoformat(),
            "tags": list(doc.tags),
        }

    async def search_documents(
        self,
        query: str,
        entity_id: str | None = None,
        category: str | None = None,
    ) -> list[dict]:
        """Search documents with optional entity and category filters."""
        doc_category = DocumentCategory(category) if category else None
        results = await self._search.search(query, entity_id=entity_id, category=doc_category)

        return [
            {
                "doc_id": r.doc_id,
                "name": r.name,
                "category": r.category.value,
                "relevance_score": r.relevance_score,
                "snippet": r.snippet,
            }
            for r in results
        ]

    async def get_versions(self, doc_id: str) -> list[dict]:
        """Return all versions of a document."""
        versions = await self._versions.get_versions(doc_id)
        return [
            {
                "version_id": v.version_id,
                "doc_id": v.doc_id,
                "version_number": v.version_number,
                "content_hash": v.content_hash,
                "change_note": v.change_note,
                "created_by": v.created_by,
                "created_at": v.created_at.isoformat(),
            }
            for v in versions
        ]

    async def check_retention_status(self, entity_id: str) -> list[dict]:
        """Return retention check results for documents requiring action."""
        return await self._retention.apply_retention_check(entity_id)

    async def delete_document(
        self,
        doc_id: str,
        actor: str,
        role: str,
    ) -> dict:
        """
        Document deletion always requires HITL (I-27).

        Deletion is irreversible and requires Compliance Officer approval.
        Always returns HITL_REQUIRED — never auto-deletes.
        """
        return {
            "status": "HITL_REQUIRED",
            "reason": ("Document deletion requires Compliance Officer approval — cannot be undone"),
        }
