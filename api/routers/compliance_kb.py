"""
api/routers/compliance_kb.py — Compliance Knowledge Base REST endpoints
IL-CKS-01 | banxe-emi-stack

8 endpoints for the compliance knowledge base:
  GET  /v1/kb/health              — service health
  GET  /v1/kb/notebooks           — list notebooks (filterable)
  GET  /v1/kb/notebooks/{id}      — get notebook details + sources
  POST /v1/kb/query               — RAG query with citations
  POST /v1/kb/search              — semantic search
  POST /v1/kb/compare             — regulatory version comparison
  GET  /v1/kb/citations/{id}      — get citation details by source ID
  POST /v1/kb/ingest              — ingest a document into a notebook

FCA: all requests logged with X-Request-ID (I-24). No PII in logs (I-09).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from services.compliance_kb.kb_service import ComplianceKBService, get_kb_service
from services.compliance_kb.storage.models import (
    Citation,
    IngestRequest,
    IngestResult,
    KBQueryRequest,
    KBQueryResult,
    KBSearchRequest,
    KBSearchResult,
    NotebookMetadata,
    VersionCompareRequest,
    VersionCompareResult,
)

logger = logging.getLogger("banxe.api.compliance_kb")
router = APIRouter(prefix="/v1/kb", tags=["Compliance KB"])


# ── Dependency ─────────────────────────────────────────────────────────────


def get_service() -> ComplianceKBService:
    """FastAPI dependency — returns the singleton KB service."""
    return get_kb_service()


# ── Health ─────────────────────────────────────────────────────────────────


class KBHealthResponse(BaseModel):
    status: str
    notebooks: int
    version: str = "1.0.0"


@router.get("/health", response_model=KBHealthResponse, summary="KB health check")
def kb_health(service: ComplianceKBService = Depends(get_service)) -> KBHealthResponse:
    """Liveness check for the compliance KB service."""
    notebooks = service.list_notebooks()
    return KBHealthResponse(status="ok", notebooks=len(notebooks))


# ── List notebooks ─────────────────────────────────────────────────────────


@router.get("/notebooks", response_model=list[NotebookMetadata], summary="List notebooks")
def list_notebooks(
    tags: list[str] | None = Query(default=None),
    jurisdiction: str | None = Query(default=None),
    service: ComplianceKBService = Depends(get_service),
) -> list[NotebookMetadata]:
    """List all compliance notebooks.

    Optional filters:
    - tags: filter by one or more tags (e.g. ?tags=aml&tags=uk)
    - jurisdiction: filter by jurisdiction (eu | uk | fatf | eba | esma)
    """
    return service.list_notebooks(tags=tags, jurisdiction=jurisdiction)


# ── Get notebook ───────────────────────────────────────────────────────────


@router.get("/notebooks/{notebook_id}", response_model=NotebookMetadata, summary="Get notebook")
def get_notebook(
    notebook_id: str,
    service: ComplianceKBService = Depends(get_service),
) -> NotebookMetadata:
    """Return full notebook metadata including source list and doc count."""
    notebook = service.get_notebook(notebook_id)
    if notebook is None:
        raise HTTPException(status_code=404, detail=f"Notebook '{notebook_id}' not found")
    return notebook


# ── RAG Query ──────────────────────────────────────────────────────────────


@router.post("/query", response_model=KBQueryResult, summary="RAG query")
def query_kb(
    request: KBQueryRequest,
    service: ComplianceKBService = Depends(get_service),
) -> KBQueryResult:
    """Ask a compliance question against a notebook.

    Returns an answer synthesised from retrieved chunks, with citations
    showing source document, section, and snippet.

    Context fields (optional):
    - jurisdiction: "uk" | "eu" | "fatf"
    - risk_level: "low" | "medium" | "high"
    - product_type: "emi" | "bank" | "crypto"
    """
    try:
        return service.query(request)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("KB query failed: %s", exc)
        raise HTTPException(status_code=500, detail="KB query failed") from exc


# ── Semantic Search ────────────────────────────────────────────────────────


@router.post("/search", response_model=list[KBSearchResult], summary="Semantic search")
def search_kb(
    request: KBSearchRequest,
    service: ComplianceKBService = Depends(get_service),
) -> list[KBSearchResult]:
    """Semantic similarity search over a compliance notebook.

    Returns raw chunks with similarity scores (higher is more relevant).
    Use this for exploratory search; use /query for synthesised answers.
    """
    try:
        return service.search(request)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("KB search failed: %s", exc)
        raise HTTPException(status_code=500, detail="KB search failed") from exc


# ── Version Comparison ─────────────────────────────────────────────────────


@router.post("/compare", response_model=VersionCompareResult, summary="Compare regulation versions")
def compare_versions(
    request: VersionCompareRequest,
    service: ComplianceKBService = Depends(get_service),
) -> VersionCompareResult:
    """Compare two versions of a regulatory document.

    Returns a structured diff showing added, removed, and modified sections
    with impact tags (e.g. 'new-requirement', 'modified-requirement').

    Both versions must be ingested into the KB before comparison.
    """
    try:
        return service.compare_versions(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("KB version compare failed: %s", exc)
        raise HTTPException(status_code=500, detail="Version comparison failed") from exc


# ── Citations ──────────────────────────────────────────────────────────────


@router.get("/citations/{source_id}", response_model=Citation, summary="Get citation details")
def get_citation(
    source_id: str,
    notebook_id: str = Query(..., description="Notebook containing this source"),
    service: ComplianceKBService = Depends(get_service),
) -> Citation:
    """Return citation details for a specific source document.

    Searches the specified notebook for the source and returns its
    metadata including title, version, URL, and a representative snippet.
    """
    notebook = service.get_notebook(notebook_id)
    if notebook is None:
        raise HTTPException(status_code=404, detail=f"Notebook '{notebook_id}' not found")

    source = next((s for s in notebook.sources if s.id == source_id), None)
    if source is None:
        raise HTTPException(
            status_code=404,
            detail=f"Source '{source_id}' not found in notebook '{notebook_id}'",
        )

    return Citation(
        source_id=source.id,
        source_type=source.source_type,
        title=source.name,
        section="Full Document",
        snippet=f"{source.name} — {source.source_type.value} ({source.version})",
        uri=source.url,
        version=source.version,
    )


# ── Ingest ─────────────────────────────────────────────────────────────────


@router.post("/ingest", response_model=IngestResult, summary="Ingest document")
def ingest_document(
    request: IngestRequest,
    service: ComplianceKBService = Depends(get_service),
) -> IngestResult:
    """Ingest a document into a compliance notebook.

    Accepts:
    - content: raw text string
    - file_path: path to PDF (.pdf), Markdown (.md), or text (.txt) file

    The document is chunked, embedded, and stored in the notebook's
    ChromaDB collection. Existing chunks for the same document_id are
    replaced on next ingest (delete + re-add pattern).
    """
    try:
        return service.ingest(request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("KB ingest failed: %s", exc)
        raise HTTPException(status_code=500, detail="Ingest failed") from exc
