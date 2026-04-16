"""
tests/test_document_management/test_document_store.py — DocumentStoreService tests
IL-DMS-01 | Phase 24 | banxe-emi-stack

16+ tests covering upload (SHA-256 hash), get, archive, dedup by hash, list by category.
"""

from __future__ import annotations

import hashlib

import pytest

from services.document_management.document_store import DocumentStoreService
from services.document_management.models import (
    AccessLevel,
    DocumentCategory,
    DocumentStatus,
    InMemoryAccessLog,
    InMemoryDocumentStore,
    InMemoryVersionStore,
)


def _make_service():
    return DocumentStoreService(
        document_store=InMemoryDocumentStore(),
        version_store=InMemoryVersionStore(),
        access_log=InMemoryAccessLog(),
    )


@pytest.mark.asyncio
async def test_upload_returns_document():
    svc = _make_service()
    doc = await svc.upload(
        name="kyc-passport.pdf",
        category=DocumentCategory.KYC,
        content="passport content",
        entity_id="entity-001",
        uploaded_by="user-001",
        access_level=AccessLevel.CONFIDENTIAL,
    )
    assert doc.doc_id is not None
    assert doc.name == "kyc-passport.pdf"
    assert doc.status == DocumentStatus.ACTIVE


@pytest.mark.asyncio
async def test_upload_computes_sha256_hash():
    svc = _make_service()
    content = "important document content"
    expected_hash = hashlib.sha256(content.encode()).hexdigest()
    doc = await svc.upload(
        name="contract.txt",
        category=DocumentCategory.CONTRACT,
        content=content,
        entity_id="entity-001",
        uploaded_by="user-001",
        access_level=AccessLevel.INTERNAL,
    )
    assert doc.content_hash == expected_hash


@pytest.mark.asyncio
async def test_upload_computes_size_bytes():
    svc = _make_service()
    content = "hello world"
    doc = await svc.upload(
        name="test.txt",
        category=DocumentCategory.POLICY,
        content=content,
        entity_id="entity-001",
        uploaded_by="user-001",
        access_level=AccessLevel.PUBLIC,
    )
    assert doc.size_bytes == len(content.encode("utf-8"))


@pytest.mark.asyncio
async def test_upload_stores_tags():
    svc = _make_service()
    doc = await svc.upload(
        name="aml-report.pdf",
        category=DocumentCategory.AML,
        content="aml content",
        entity_id="entity-001",
        uploaded_by="user-001",
        access_level=AccessLevel.RESTRICTED,
        tags=("aml", "report", "2026"),
    )
    assert "aml" in doc.tags
    assert "report" in doc.tags


@pytest.mark.asyncio
async def test_upload_creates_initial_version():
    doc_store = InMemoryDocumentStore()
    version_store = InMemoryVersionStore()
    svc = DocumentStoreService(
        document_store=doc_store,
        version_store=version_store,
        access_log=InMemoryAccessLog(),
    )
    doc = await svc.upload(
        name="policy.pdf",
        category=DocumentCategory.POLICY,
        content="policy content",
        entity_id="entity-001",
        uploaded_by="user-001",
        access_level=AccessLevel.INTERNAL,
    )
    versions = await version_store.list_versions(doc.doc_id)
    assert len(versions) == 1
    assert versions[0].version_number == 1
    assert versions[0].change_note == "Initial upload"


@pytest.mark.asyncio
async def test_upload_logs_access_record():
    doc_store = InMemoryDocumentStore()
    access_log = InMemoryAccessLog()
    svc = DocumentStoreService(
        document_store=doc_store,
        version_store=InMemoryVersionStore(),
        access_log=access_log,
    )
    doc = await svc.upload(
        name="doc.txt",
        category=DocumentCategory.KYC,
        content="content",
        entity_id="entity-001",
        uploaded_by="user-001",
        access_level=AccessLevel.INTERNAL,
    )
    records = await access_log.list_access(doc.doc_id)
    assert len(records) == 1
    assert records[0].action == "VIEW"


@pytest.mark.asyncio
async def test_get_document_returns_doc():
    svc = _make_service()
    uploaded = await svc.upload(
        name="doc.txt",
        category=DocumentCategory.KYC,
        content="content",
        entity_id="entity-001",
        uploaded_by="user-001",
        access_level=AccessLevel.INTERNAL,
    )
    doc = await svc.get_document(uploaded.doc_id, "user-002")
    assert doc is not None
    assert doc.doc_id == uploaded.doc_id


@pytest.mark.asyncio
async def test_get_document_returns_none_for_missing():
    svc = _make_service()
    doc = await svc.get_document("nonexistent-id", "user-001")
    assert doc is None


@pytest.mark.asyncio
async def test_get_document_logs_access():
    doc_store = InMemoryDocumentStore()
    access_log = InMemoryAccessLog()
    svc = DocumentStoreService(
        document_store=doc_store,
        version_store=InMemoryVersionStore(),
        access_log=access_log,
    )
    uploaded = await svc.upload(
        name="doc.txt",
        category=DocumentCategory.KYC,
        content="content",
        entity_id="entity-001",
        uploaded_by="user-001",
        access_level=AccessLevel.INTERNAL,
    )
    await svc.get_document(uploaded.doc_id, "user-002")
    records = await access_log.list_access(uploaded.doc_id)
    # upload logs 1, get logs 1 more = 2
    assert len(records) == 2


@pytest.mark.asyncio
async def test_archive_document_changes_status():
    svc = _make_service()
    doc = await svc.upload(
        name="doc.txt",
        category=DocumentCategory.KYC,
        content="content",
        entity_id="entity-001",
        uploaded_by="user-001",
        access_level=AccessLevel.INTERNAL,
    )
    archived = await svc.archive_document(doc.doc_id, "admin-001")
    assert archived.status == DocumentStatus.ARCHIVED


@pytest.mark.asyncio
async def test_archive_nonexistent_raises():
    svc = _make_service()
    with pytest.raises(ValueError):
        await svc.archive_document("nonexistent-id", "admin-001")


@pytest.mark.asyncio
async def test_list_documents_by_entity():
    svc = _make_service()
    await svc.upload(
        name="doc1.txt",
        category=DocumentCategory.KYC,
        content="content1",
        entity_id="entity-001",
        uploaded_by="user-001",
        access_level=AccessLevel.INTERNAL,
    )
    await svc.upload(
        name="doc2.txt",
        category=DocumentCategory.AML,
        content="content2",
        entity_id="entity-001",
        uploaded_by="user-001",
        access_level=AccessLevel.INTERNAL,
    )
    await svc.upload(
        name="doc3.txt",
        category=DocumentCategory.KYC,
        content="content3",
        entity_id="entity-002",
        uploaded_by="user-001",
        access_level=AccessLevel.INTERNAL,
    )
    docs = await svc.list_documents("entity-001")
    assert len(docs) == 2


@pytest.mark.asyncio
async def test_list_documents_filtered_by_category():
    svc = _make_service()
    await svc.upload(
        name="kyc.txt",
        category=DocumentCategory.KYC,
        content="kyc content",
        entity_id="entity-001",
        uploaded_by="user-001",
        access_level=AccessLevel.INTERNAL,
    )
    await svc.upload(
        name="aml.txt",
        category=DocumentCategory.AML,
        content="aml content",
        entity_id="entity-001",
        uploaded_by="user-001",
        access_level=AccessLevel.INTERNAL,
    )
    docs = await svc.list_documents("entity-001", category=DocumentCategory.KYC)
    assert len(docs) == 1
    assert docs[0].category == DocumentCategory.KYC


@pytest.mark.asyncio
async def test_get_document_by_hash_finds_existing():
    svc = _make_service()
    content = "unique document content"
    expected_hash = hashlib.sha256(content.encode()).hexdigest()
    await svc.upload(
        name="doc.txt",
        category=DocumentCategory.KYC,
        content=content,
        entity_id="entity-001",
        uploaded_by="user-001",
        access_level=AccessLevel.INTERNAL,
    )
    doc = await svc.get_document_by_hash(expected_hash)
    assert doc is not None
    assert doc.content_hash == expected_hash


@pytest.mark.asyncio
async def test_get_document_by_hash_returns_none_for_missing():
    svc = _make_service()
    doc = await svc.get_document_by_hash("nonexistent-hash")
    assert doc is None


@pytest.mark.asyncio
async def test_upload_mime_type_default():
    svc = _make_service()
    doc = await svc.upload(
        name="doc.txt",
        category=DocumentCategory.KYC,
        content="content",
        entity_id="entity-001",
        uploaded_by="user-001",
        access_level=AccessLevel.INTERNAL,
    )
    assert doc.mime_type == "text/plain"
