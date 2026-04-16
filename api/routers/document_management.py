"""
api/routers/document_management.py — Document Management System endpoints
IL-DMS-01 | Phase 24 | banxe-emi-stack

POST   /v1/documents/upload                  — upload document
GET    /v1/documents/retention-policies      — list retention policies
GET    /v1/documents/retention/{entity_id}   — check retention status for entity
POST   /v1/documents/search                  — keyword search
GET    /v1/documents/{doc_id}                — get document
GET    /v1/documents/{doc_id}/versions       — get document versions
GET    /v1/documents/{doc_id}/access-log     — get access log
DELETE /v1/documents/{doc_id}                — delete (always HITL_REQUIRED)
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.document_management.access_controller import AccessController
from services.document_management.document_agent import DocumentAgent
from services.document_management.document_store import DocumentStoreService
from services.document_management.models import (
    InMemoryAccessLog,
    InMemoryDocumentStore,
    InMemoryRetentionStore,
    InMemorySearchIndex,
    InMemoryVersionStore,
)
from services.document_management.retention_engine import RetentionEngine
from services.document_management.search_engine import SearchEngine
from services.document_management.version_manager import VersionManager

router = APIRouter(tags=["document-management"])


# ── Pydantic request models ────────────────────────────────────────────────────


class UploadRequest(BaseModel):
    name: str
    category: str
    content: str
    entity_id: str
    uploaded_by: str
    role: str
    access_level: str = "INTERNAL"
    tags: list[str] = []


class SearchRequest(BaseModel):
    query: str
    entity_id: str | None = None
    category: str | None = None


class DeleteRequest(BaseModel):
    doc_id: str
    actor: str
    role: str


# ── Agent factory (cached) ─────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _get_agent() -> DocumentAgent:
    doc_store = InMemoryDocumentStore()
    version_store = InMemoryVersionStore()
    retention_store = InMemoryRetentionStore()
    search_index = InMemorySearchIndex()
    access_log = InMemoryAccessLog()

    document_store_svc = DocumentStoreService(
        document_store=doc_store,
        version_store=version_store,
        access_log=access_log,
    )
    version_manager = VersionManager(
        document_store=doc_store,
        version_store=version_store,
        access_log=access_log,
    )
    retention_engine = RetentionEngine(
        retention_store=retention_store,
        document_store=doc_store,
        access_log=access_log,
    )
    search_engine = SearchEngine(
        search_index=search_index,
        document_store=doc_store,
    )
    access_controller = AccessController(
        access_log=access_log,
        document_store=doc_store,
    )

    return DocumentAgent(
        document_store=document_store_svc,
        version_manager=version_manager,
        retention_engine=retention_engine,
        search_engine=search_engine,
        access_controller=access_controller,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post(
    "/v1/documents/upload",
    status_code=201,
    summary="Upload a new document",
)
async def upload_document(body: UploadRequest) -> dict:
    """Upload a document with SHA-256 integrity hash. Returns document metadata."""
    agent = _get_agent()
    return await agent.upload_document(
        name=body.name,
        category=body.category,
        content=body.content,
        entity_id=body.entity_id,
        uploaded_by=body.uploaded_by,
        role=body.role,
        access_level=body.access_level,
        tags=body.tags,
    )


@router.get(
    "/v1/documents/retention-policies",
    summary="List all retention policies",
)
async def list_retention_policies() -> list[dict]:
    """Return all configured document retention policies."""
    agent = _get_agent()
    policies = await agent._retention.list_policies()
    return [
        {
            "policy_id": p.policy_id,
            "category": p.category.value,
            "retention_period": p.retention_period.value,
            "auto_delete": p.auto_delete,
            "regulatory_basis": p.regulatory_basis,
        }
        for p in policies
    ]


@router.get(
    "/v1/documents/retention/{entity_id}",
    summary="Check retention status for an entity's documents",
)
async def check_retention_status(entity_id: str) -> list[dict]:
    """Return documents that have exceeded their retention period."""
    agent = _get_agent()
    return await agent.check_retention_status(entity_id)


@router.post(
    "/v1/documents/search",
    summary="Search documents by keyword",
)
async def search_documents(body: SearchRequest) -> list[dict]:
    """Search documents. Optionally filter by entity_id and category."""
    agent = _get_agent()
    return await agent.search_documents(
        query=body.query,
        entity_id=body.entity_id,
        category=body.category,
    )


@router.get(
    "/v1/documents/{doc_id}",
    summary="Get document by ID",
)
async def get_document(
    doc_id: str,
    accessed_by: str,
    role: str,
) -> dict:
    """Retrieve a document. Returns 403 if role lacks access, 404 if not found."""
    agent = _get_agent()
    result = await agent.get_document(doc_id=doc_id, accessed_by=accessed_by, role=role)
    if result is None:
        doc = await agent._store._docs.get(doc_id)
        if doc is None:
            raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")
        raise HTTPException(status_code=403, detail="Access denied")
    return result


@router.get(
    "/v1/documents/{doc_id}/versions",
    summary="Get document version history",
)
async def get_versions(doc_id: str) -> list[dict]:
    """Return all versions of a document sorted by version number."""
    agent = _get_agent()
    return await agent.get_versions(doc_id)


@router.get(
    "/v1/documents/{doc_id}/access-log",
    summary="Get document access log",
)
async def get_access_log(doc_id: str) -> list[dict]:
    """Return the append-only access log for a document (I-24)."""
    agent = _get_agent()
    records = await agent._access.get_access_log(doc_id)
    return [
        {
            "record_id": r.record_id,
            "doc_id": r.doc_id,
            "accessed_by": r.accessed_by,
            "action": r.action,
            "ip_address": r.ip_address,
            "accessed_at": r.accessed_at.isoformat(),
        }
        for r in records
    ]


@router.delete(
    "/v1/documents/{doc_id}",
    status_code=202,
    summary="Delete document (always HITL_REQUIRED)",
)
async def delete_document(doc_id: str, actor: str, role: str) -> dict:
    """
    Document deletion always requires Compliance Officer approval (I-27).
    Always returns 202 HITL_REQUIRED — never auto-deletes.
    """
    agent = _get_agent()
    return await agent.delete_document(doc_id=doc_id, actor=actor, role=role)
