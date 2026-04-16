"""
services/document_management/models.py — Domain models, enums, ports, and in-memory stubs
IL-DMS-01 | Phase 24 | banxe-emi-stack
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol
import uuid

# ── Enums ─────────────────────────────────────────────────────────────────────


class DocumentCategory(str, Enum):
    KYC = "KYC"
    AML = "AML"
    POLICY = "POLICY"
    REPORT = "REPORT"
    CONTRACT = "CONTRACT"
    REGULATORY = "REGULATORY"
    AUDIT = "AUDIT"


class DocumentStatus(str, Enum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"
    DELETED = "DELETED"
    SUPERSEDED = "SUPERSEDED"


class AccessLevel(str, Enum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    RESTRICTED = "RESTRICTED"


class RetentionPeriod(str, Enum):
    YEARS_5 = "YEARS_5"
    YEARS_7 = "YEARS_7"
    YEARS_10 = "YEARS_10"
    PERMANENT = "PERMANENT"


# ── Frozen Dataclasses ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Document:
    doc_id: str
    name: str
    category: DocumentCategory
    content_hash: str
    size_bytes: int
    mime_type: str
    status: DocumentStatus
    access_level: AccessLevel
    entity_id: str
    uploaded_by: str
    created_at: datetime
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class DocumentVersion:
    version_id: str
    doc_id: str
    version_number: int
    content_hash: str
    change_note: str
    created_by: str
    created_at: datetime


@dataclass(frozen=True)
class RetentionPolicy:
    policy_id: str
    category: DocumentCategory
    retention_period: RetentionPeriod
    auto_delete: bool
    regulatory_basis: str


@dataclass(frozen=True)
class AccessRecord:
    record_id: str
    doc_id: str
    accessed_by: str
    action: str  # "VIEW", "DOWNLOAD", "UPDATE", "DELETE", "ACCESS_DENIED"
    ip_address: str
    accessed_at: datetime


@dataclass(frozen=True)
class DocumentSearchResult:
    doc_id: str
    name: str
    category: DocumentCategory
    relevance_score: float  # analytical score, not monetary
    snippet: str


# ── Protocols ─────────────────────────────────────────────────────────────────


class DocumentStorePort(Protocol):
    async def save(self, doc: Document) -> Document: ...

    async def get(self, doc_id: str) -> Document | None: ...

    async def list_by_entity(
        self,
        entity_id: str,
        category: DocumentCategory | None = None,
    ) -> list[Document]: ...

    async def update(self, doc: Document) -> Document: ...


class VersionStorePort(Protocol):
    async def save_version(self, v: DocumentVersion) -> DocumentVersion: ...

    async def list_versions(self, doc_id: str) -> list[DocumentVersion]: ...

    async def get_version(self, version_id: str) -> DocumentVersion | None: ...


class RetentionStorePort(Protocol):
    async def get_policy(self, category: DocumentCategory) -> RetentionPolicy | None: ...

    async def list_policies(self) -> list[RetentionPolicy]: ...

    async def save_policy(self, p: RetentionPolicy) -> RetentionPolicy: ...


class AccessLogPort(Protocol):
    async def log_access(self, record: AccessRecord) -> AccessRecord: ...

    async def list_access(self, doc_id: str) -> list[AccessRecord]: ...


class SearchIndexPort(Protocol):
    async def index(self, doc: Document, content: str) -> None: ...

    async def search(
        self,
        query: str,
        category: DocumentCategory | None = None,
    ) -> list[DocumentSearchResult]: ...


# ── InMemory Stubs ────────────────────────────────────────────────────────────


class InMemoryDocumentStore:
    """In-memory document store for tests."""

    def __init__(self) -> None:
        self._store: dict[str, Document] = {}

    async def save(self, doc: Document) -> Document:
        self._store[doc.doc_id] = doc
        return doc

    async def get(self, doc_id: str) -> Document | None:
        return self._store.get(doc_id)

    async def list_by_entity(
        self,
        entity_id: str,
        category: DocumentCategory | None = None,
    ) -> list[Document]:
        docs = [d for d in self._store.values() if d.entity_id == entity_id]
        if category is not None:
            docs = [d for d in docs if d.category == category]
        return docs

    async def update(self, doc: Document) -> Document:
        self._store[doc.doc_id] = doc
        return doc


class InMemoryVersionStore:
    """In-memory version store for tests."""

    def __init__(self) -> None:
        self._store: dict[str, DocumentVersion] = {}

    async def save_version(self, v: DocumentVersion) -> DocumentVersion:
        self._store[v.version_id] = v
        return v

    async def list_versions(self, doc_id: str) -> list[DocumentVersion]:
        return [v for v in self._store.values() if v.doc_id == doc_id]

    async def get_version(self, version_id: str) -> DocumentVersion | None:
        return self._store.get(version_id)


class InMemoryRetentionStore:
    """In-memory retention store pre-seeded with default policies."""

    def __init__(self) -> None:
        self._store: dict[str, RetentionPolicy] = {}
        self._seed_defaults()

    def _seed_defaults(self) -> None:
        defaults = [
            RetentionPolicy(
                policy_id=str(uuid.uuid4()),
                category=DocumentCategory.KYC,
                retention_period=RetentionPeriod.YEARS_5,
                auto_delete=False,
                regulatory_basis="MLR 2017 Reg.40 — 5yr post-relationship",
            ),
            RetentionPolicy(
                policy_id=str(uuid.uuid4()),
                category=DocumentCategory.AML,
                retention_period=RetentionPeriod.YEARS_5,
                auto_delete=False,
                regulatory_basis="MLR 2017 Reg.40 — AML records 5yr",
            ),
            RetentionPolicy(
                policy_id=str(uuid.uuid4()),
                category=DocumentCategory.POLICY,
                retention_period=RetentionPeriod.PERMANENT,
                auto_delete=False,
                regulatory_basis="SYSC 9 — permanent record",
            ),
            RetentionPolicy(
                policy_id=str(uuid.uuid4()),
                category=DocumentCategory.REPORT,
                retention_period=RetentionPeriod.YEARS_7,
                auto_delete=False,
                regulatory_basis="SYSC 9 — regulatory reports 7yr",
            ),
            RetentionPolicy(
                policy_id=str(uuid.uuid4()),
                category=DocumentCategory.CONTRACT,
                retention_period=RetentionPeriod.YEARS_7,
                auto_delete=False,
                regulatory_basis="Standard contract retention",
            ),
            RetentionPolicy(
                policy_id=str(uuid.uuid4()),
                category=DocumentCategory.REGULATORY,
                retention_period=RetentionPeriod.PERMANENT,
                auto_delete=False,
                regulatory_basis="SYSC 9 — regulatory submissions",
            ),
        ]
        for policy in defaults:
            self._store[policy.category.value] = policy

    async def get_policy(self, category: DocumentCategory) -> RetentionPolicy | None:
        return self._store.get(category.value)

    async def list_policies(self) -> list[RetentionPolicy]:
        return list(self._store.values())

    async def save_policy(self, p: RetentionPolicy) -> RetentionPolicy:
        self._store[p.category.value] = p
        return p


class InMemoryAccessLog:
    """In-memory access log — append-only (I-24)."""

    def __init__(self) -> None:
        self._records: list[AccessRecord] = []

    async def log_access(self, record: AccessRecord) -> AccessRecord:
        self._records.append(record)
        return record

    async def list_access(self, doc_id: str) -> list[AccessRecord]:
        return [r for r in self._records if r.doc_id == doc_id]


class InMemorySearchIndex:
    """In-memory search index with basic keyword matching."""

    def __init__(self) -> None:
        self._index: dict[str, tuple[Document, str]] = {}

    async def index(self, doc: Document, content: str) -> None:
        self._index[doc.doc_id] = (doc, content)

    async def search(
        self,
        query: str,
        category: DocumentCategory | None = None,
    ) -> list[DocumentSearchResult]:
        query_words = set(query.lower().split())
        results: list[DocumentSearchResult] = []

        for doc, _content in self._index.values():
            if category is not None and doc.category != category:
                continue

            name_words = set(doc.name.lower().split())
            tag_words: set[str] = set()
            for tag in doc.tags:
                tag_words.update(tag.lower().split())

            name_match = bool(query_words & name_words)
            tag_match = bool(query_words & tag_words)

            if name_match:
                score = 1.0
            elif tag_match:
                score = 0.5
            else:
                continue

            results.append(
                DocumentSearchResult(
                    doc_id=doc.doc_id,
                    name=doc.name,
                    category=doc.category,
                    relevance_score=score,
                    snippet=doc.name[:100],
                )
            )

        return results
