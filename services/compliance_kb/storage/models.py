"""
services/compliance_kb/storage/models.py — Pydantic models for the KB
IL-CKS-01 | banxe-emi-stack

All models use strict typing. No float for amounts (I-01).
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    REGULATION = "regulation"
    GUIDANCE = "guidance"
    SOP = "sop"
    SAR_TEMPLATE = "sar_template"
    POLICY = "policy"
    CASE_STUDY = "case_study"


class Jurisdiction(str, Enum):
    EU = "eu"
    UK = "uk"
    FATF = "fatf"
    EBA = "eba"
    ESMA = "esma"


class ComplianceDocument(BaseModel):
    id: str = Field(..., description="Unique document ID, e.g. 'eba-gl-2021-02'")
    name: str
    source_type: SourceType
    jurisdiction: Jurisdiction
    version: str = Field(..., description="ISO date, e.g. '2021-06-01'")
    tags: list[str] = Field(default_factory=list)
    file_path: str | None = None
    url: str | None = None
    doc_count: int = 0
    sections: list[str] = Field(default_factory=list)


class DocumentChunk(BaseModel):
    chunk_id: str
    document_id: str
    section: str
    text: str
    page: int | None = None
    char_start: int
    char_end: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class Citation(BaseModel):
    source_id: str
    source_type: SourceType
    title: str
    section: str
    snippet: str
    uri: str | None = None
    version: str


# ── Request / Response models ──────────────────────────────────────────────


class KBQueryRequest(BaseModel):
    notebook_id: str
    question: str
    context: dict[str, str] = Field(default_factory=dict)
    max_citations: int = Field(default=10, ge=1, le=20)


class KBQueryResult(BaseModel):
    question: str
    answer: str
    citations: list[Citation]
    notebook_id: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class KBSearchRequest(BaseModel):
    notebook_id: str
    query: str
    limit: int = Field(default=10, ge=1, le=50)


class KBSearchResult(BaseModel):
    chunk_id: str
    document_id: str
    text: str
    section: str
    score: float = Field(ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class VersionCompareRequest(BaseModel):
    source_id: str
    from_version: str
    to_version: str
    focus_sections: list[str] = Field(default_factory=list)


class VersionChange(BaseModel):
    section: str
    change_type: str  # "added" | "removed" | "modified"
    before: str | None = None
    after: str | None = None
    impact_tags: list[str] = Field(default_factory=list)


class VersionCompareResult(BaseModel):
    source_id: str
    from_version: str
    to_version: str
    diff_summary: str
    changes: list[VersionChange]


class NotebookSource(BaseModel):
    id: str
    name: str
    source_type: SourceType
    url: str | None = None
    version: str = "latest"


class NotebookMetadata(BaseModel):
    id: str
    name: str
    description: str
    tags: list[str]
    jurisdiction: Jurisdiction
    sources: list[NotebookSource]
    doc_count: int = 0


class IngestRequest(BaseModel):
    notebook_id: str
    document_id: str
    name: str
    source_type: SourceType
    jurisdiction: Jurisdiction
    version: str
    tags: list[str] = Field(default_factory=list)
    content: str | None = None
    url: str | None = None
    file_path: str | None = None


class IngestResult(BaseModel):
    document_id: str
    notebook_id: str
    chunks_created: int
    status: str = "ok"
