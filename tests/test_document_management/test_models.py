"""
tests/test_document_management/test_models.py — Model and stub tests
IL-DMS-01 | Phase 24 | banxe-emi-stack

18+ tests covering enums, frozen dataclasses, retention policy seeding,
InMemory stubs, and DocumentSearchResult.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
import uuid

import pytest

from services.document_management.models import (
    AccessLevel,
    AccessRecord,
    Document,
    DocumentCategory,
    DocumentSearchResult,
    DocumentStatus,
    DocumentVersion,
    InMemoryAccessLog,
    InMemoryRetentionStore,
    InMemorySearchIndex,
    RetentionPeriod,
    RetentionPolicy,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _make_doc(**kwargs) -> Document:
    defaults = dict(
        doc_id=str(uuid.uuid4()),
        name="test-document.pdf",
        category=DocumentCategory.KYC,
        content_hash="abc123",
        size_bytes=1024,
        mime_type="application/pdf",
        status=DocumentStatus.ACTIVE,
        access_level=AccessLevel.INTERNAL,
        entity_id="entity-001",
        uploaded_by="user-001",
        created_at=_now(),
        tags=(),
    )
    defaults.update(kwargs)
    return Document(**defaults)


# ── Enum tests ────────────────────────────────────────────────────────────────


def test_document_category_values():
    assert DocumentCategory.KYC.value == "KYC"
    assert DocumentCategory.AML.value == "AML"
    assert DocumentCategory.POLICY.value == "POLICY"
    assert DocumentCategory.REPORT.value == "REPORT"
    assert DocumentCategory.CONTRACT.value == "CONTRACT"
    assert DocumentCategory.REGULATORY.value == "REGULATORY"
    assert DocumentCategory.AUDIT.value == "AUDIT"


def test_document_status_values():
    assert DocumentStatus.ACTIVE.value == "ACTIVE"
    assert DocumentStatus.ARCHIVED.value == "ARCHIVED"
    assert DocumentStatus.DELETED.value == "DELETED"
    assert DocumentStatus.SUPERSEDED.value == "SUPERSEDED"


def test_access_level_values():
    assert AccessLevel.PUBLIC.value == "PUBLIC"
    assert AccessLevel.INTERNAL.value == "INTERNAL"
    assert AccessLevel.CONFIDENTIAL.value == "CONFIDENTIAL"
    assert AccessLevel.RESTRICTED.value == "RESTRICTED"


def test_retention_period_values():
    assert RetentionPeriod.YEARS_5.value == "YEARS_5"
    assert RetentionPeriod.YEARS_7.value == "YEARS_7"
    assert RetentionPeriod.YEARS_10.value == "YEARS_10"
    assert RetentionPeriod.PERMANENT.value == "PERMANENT"


# ── Frozen dataclass tests ────────────────────────────────────────────────────


def test_document_is_frozen():
    doc = _make_doc()
    with pytest.raises(FrozenInstanceError):
        doc.name = "modified"  # type: ignore[misc]


def test_document_tags_default_empty_tuple():
    doc = _make_doc()
    assert doc.tags == ()


def test_document_with_tags():
    doc = _make_doc(tags=("kyc", "passport"))
    assert "kyc" in doc.tags
    assert len(doc.tags) == 2


def test_document_version_frozen():
    v = DocumentVersion(
        version_id=str(uuid.uuid4()),
        doc_id="doc-001",
        version_number=1,
        content_hash="hash123",
        change_note="Initial upload",
        created_by="user-001",
        created_at=_now(),
    )
    with pytest.raises(FrozenInstanceError):
        v.version_number = 2  # type: ignore[misc]


def test_retention_policy_frozen():
    p = RetentionPolicy(
        policy_id=str(uuid.uuid4()),
        category=DocumentCategory.KYC,
        retention_period=RetentionPeriod.YEARS_5,
        auto_delete=False,
        regulatory_basis="MLR 2017",
    )
    with pytest.raises(FrozenInstanceError):
        p.auto_delete = True  # type: ignore[misc]


def test_access_record_frozen():
    r = AccessRecord(
        record_id=str(uuid.uuid4()),
        doc_id="doc-001",
        accessed_by="user-001",
        action="VIEW",
        ip_address="127.0.0.1",
        accessed_at=_now(),
    )
    with pytest.raises(FrozenInstanceError):
        r.action = "DELETE"  # type: ignore[misc]


def test_document_search_result_relevance_is_float():
    result = DocumentSearchResult(
        doc_id="doc-001",
        name="test doc",
        category=DocumentCategory.KYC,
        relevance_score=0.75,
        snippet="test snippet",
    )
    assert isinstance(result.relevance_score, float)
    assert result.relevance_score == 0.75


# ── InMemoryRetentionStore seeding tests ──────────────────────────────────────


@pytest.mark.asyncio
async def test_retention_store_seeded_kyc():
    store = InMemoryRetentionStore()
    policy = await store.get_policy(DocumentCategory.KYC)
    assert policy is not None
    assert policy.retention_period == RetentionPeriod.YEARS_5
    assert policy.auto_delete is False
    assert "MLR 2017" in policy.regulatory_basis


@pytest.mark.asyncio
async def test_retention_store_seeded_aml():
    store = InMemoryRetentionStore()
    policy = await store.get_policy(DocumentCategory.AML)
    assert policy is not None
    assert policy.retention_period == RetentionPeriod.YEARS_5


@pytest.mark.asyncio
async def test_retention_store_seeded_policy():
    store = InMemoryRetentionStore()
    policy = await store.get_policy(DocumentCategory.POLICY)
    assert policy is not None
    assert policy.retention_period == RetentionPeriod.PERMANENT


@pytest.mark.asyncio
async def test_retention_store_seeded_report():
    store = InMemoryRetentionStore()
    policy = await store.get_policy(DocumentCategory.REPORT)
    assert policy is not None
    assert policy.retention_period == RetentionPeriod.YEARS_7


@pytest.mark.asyncio
async def test_retention_store_seeded_regulatory():
    store = InMemoryRetentionStore()
    policy = await store.get_policy(DocumentCategory.REGULATORY)
    assert policy is not None
    assert policy.retention_period == RetentionPeriod.PERMANENT


@pytest.mark.asyncio
async def test_retention_store_list_policies_count():
    store = InMemoryRetentionStore()
    policies = await store.list_policies()
    assert len(policies) == 6


@pytest.mark.asyncio
async def test_retention_store_save_policy():
    store = InMemoryRetentionStore()
    new_policy = RetentionPolicy(
        policy_id=str(uuid.uuid4()),
        category=DocumentCategory.AUDIT,
        retention_period=RetentionPeriod.YEARS_10,
        auto_delete=False,
        regulatory_basis="Custom audit basis",
    )
    saved = await store.save_policy(new_policy)
    assert saved.category == DocumentCategory.AUDIT
    retrieved = await store.get_policy(DocumentCategory.AUDIT)
    assert retrieved is not None
    assert retrieved.retention_period == RetentionPeriod.YEARS_10


@pytest.mark.asyncio
async def test_in_memory_access_log_append_only():
    log = InMemoryAccessLog()
    record = AccessRecord(
        record_id=str(uuid.uuid4()),
        doc_id="doc-001",
        accessed_by="user-001",
        action="VIEW",
        ip_address="127.0.0.1",
        accessed_at=_now(),
    )
    await log.log_access(record)
    await log.log_access(record)
    records = await log.list_access("doc-001")
    assert len(records) == 2


@pytest.mark.asyncio
async def test_in_memory_search_index_basic():
    index = InMemorySearchIndex()
    doc = _make_doc(name="passport kyc document", tags=("identity",))
    await index.index(doc, "content")
    results = await index.search("passport")
    assert len(results) == 1
    assert results[0].relevance_score == 1.0
