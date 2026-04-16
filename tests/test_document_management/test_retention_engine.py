"""
tests/test_document_management/test_retention_engine.py — RetentionEngine tests
IL-DMS-01 | Phase 24 | banxe-emi-stack

14+ tests: get_policy, check_retention (days calc), action_required logic, PERMANENT=no action.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import uuid

import pytest

from services.document_management.document_store import DocumentStoreService
from services.document_management.models import (
    AccessLevel,
    Document,
    DocumentCategory,
    DocumentStatus,
    InMemoryAccessLog,
    InMemoryDocumentStore,
    InMemoryRetentionStore,
    InMemoryVersionStore,
    RetentionPeriod,
)
from services.document_management.retention_engine import _RETENTION_DAYS, RetentionEngine


def _make_engine():
    doc_store = InMemoryDocumentStore()
    retention_store = InMemoryRetentionStore()
    access_log = InMemoryAccessLog()
    engine = RetentionEngine(
        retention_store=retention_store,
        document_store=doc_store,
        access_log=access_log,
    )
    return engine, doc_store


def _make_doc_with_age(category: DocumentCategory, days_old: int) -> Document:
    created_at = datetime.now(UTC) - timedelta(days=days_old)
    return Document(
        doc_id=str(uuid.uuid4()),
        name="test.pdf",
        category=category,
        content_hash="hash123",
        size_bytes=100,
        mime_type="text/plain",
        status=DocumentStatus.ACTIVE,
        access_level=AccessLevel.INTERNAL,
        entity_id="entity-001",
        uploaded_by="user-001",
        created_at=created_at,
    )


@pytest.mark.asyncio
async def test_get_retention_policy_kyc():
    engine, _ = _make_engine()
    policy = await engine.get_retention_policy(DocumentCategory.KYC)
    assert policy is not None
    assert policy.retention_period == RetentionPeriod.YEARS_5


@pytest.mark.asyncio
async def test_get_retention_policy_policy_permanent():
    engine, _ = _make_engine()
    policy = await engine.get_retention_policy(DocumentCategory.POLICY)
    assert policy is not None
    assert policy.retention_period == RetentionPeriod.PERMANENT


@pytest.mark.asyncio
async def test_get_retention_policy_report_7_years():
    engine, _ = _make_engine()
    policy = await engine.get_retention_policy(DocumentCategory.REPORT)
    assert policy is not None
    assert policy.retention_period == RetentionPeriod.YEARS_7


@pytest.mark.asyncio
async def test_retention_days_mapping():
    assert _RETENTION_DAYS[RetentionPeriod.YEARS_5] == 1825
    assert _RETENTION_DAYS[RetentionPeriod.YEARS_7] == 2555
    assert _RETENTION_DAYS[RetentionPeriod.YEARS_10] == 3650
    assert _RETENTION_DAYS[RetentionPeriod.PERMANENT] is None


@pytest.mark.asyncio
async def test_check_retention_action_required_true():
    engine, _ = _make_engine()
    # KYC: 5 years = 1825 days; document is 2000 days old → action required
    doc = _make_doc_with_age(DocumentCategory.KYC, days_old=2000)
    result = await engine.check_retention(doc)
    assert result["action_required"] is True
    assert result["days_stored"] >= 2000
    assert result["retention_days"] == 1825


@pytest.mark.asyncio
async def test_check_retention_action_required_false():
    engine, _ = _make_engine()
    # KYC: 5 years = 1825 days; document is 100 days old → no action needed
    doc = _make_doc_with_age(DocumentCategory.KYC, days_old=100)
    result = await engine.check_retention(doc)
    assert result["action_required"] is False
    assert result["days_stored"] <= 200


@pytest.mark.asyncio
async def test_check_retention_permanent_no_action():
    engine, _ = _make_engine()
    # POLICY is PERMANENT → never action required, even if very old
    doc = _make_doc_with_age(DocumentCategory.POLICY, days_old=10000)
    result = await engine.check_retention(doc)
    assert result["action_required"] is False
    assert result["retention_days"] is None


@pytest.mark.asyncio
async def test_check_retention_regulatory_permanent_no_action():
    engine, _ = _make_engine()
    doc = _make_doc_with_age(DocumentCategory.REGULATORY, days_old=5000)
    result = await engine.check_retention(doc)
    assert result["action_required"] is False


@pytest.mark.asyncio
async def test_check_retention_returns_doc_id():
    engine, _ = _make_engine()
    doc = _make_doc_with_age(DocumentCategory.KYC, days_old=50)
    result = await engine.check_retention(doc)
    assert result["doc_id"] == doc.doc_id


@pytest.mark.asyncio
async def test_check_retention_returns_category_string():
    engine, _ = _make_engine()
    doc = _make_doc_with_age(DocumentCategory.AML, days_old=50)
    result = await engine.check_retention(doc)
    assert result["category"] == "AML"


@pytest.mark.asyncio
async def test_list_policies_returns_all():
    engine, _ = _make_engine()
    policies = await engine.list_policies()
    assert len(policies) >= 6


@pytest.mark.asyncio
async def test_apply_retention_check_empty_for_new_docs():
    engine, doc_store = _make_engine()
    svc = DocumentStoreService(
        document_store=doc_store,
        version_store=InMemoryVersionStore(),
        access_log=InMemoryAccessLog(),
    )
    await svc.upload(
        name="new-doc.txt",
        category=DocumentCategory.KYC,
        content="content",
        entity_id="entity-001",
        uploaded_by="user-001",
        access_level=AccessLevel.INTERNAL,
    )
    overdue = await engine.apply_retention_check("entity-001")
    assert overdue == []


@pytest.mark.asyncio
async def test_apply_retention_check_finds_overdue_docs():
    engine, doc_store = _make_engine()
    # Manually insert a doc that is 2000 days old (exceeds KYC 1825 days)
    old_doc = _make_doc_with_age(DocumentCategory.KYC, days_old=2000)
    await doc_store.save(old_doc)
    overdue = await engine.apply_retention_check("entity-001")
    assert len(overdue) == 1
    assert overdue[0]["action_required"] is True


@pytest.mark.asyncio
async def test_apply_retention_check_excludes_permanent():
    engine, doc_store = _make_engine()
    old_policy_doc = _make_doc_with_age(DocumentCategory.POLICY, days_old=5000)
    await doc_store.save(old_policy_doc)
    overdue = await engine.apply_retention_check("entity-001")
    # POLICY is PERMANENT → should not appear in overdue
    assert overdue == []
