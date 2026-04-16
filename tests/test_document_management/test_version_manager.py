"""
tests/test_document_management/test_version_manager.py — VersionManager tests
IL-DMS-01 | Phase 24 | banxe-emi-stack

14+ tests: create_version, rollback, get_latest, version numbers increment.
"""

from __future__ import annotations

import hashlib

import pytest

from services.document_management.document_store import DocumentStoreService
from services.document_management.models import (
    AccessLevel,
    DocumentCategory,
    InMemoryAccessLog,
    InMemoryDocumentStore,
    InMemoryVersionStore,
)
from services.document_management.version_manager import VersionManager


def _make_components():
    doc_store = InMemoryDocumentStore()
    version_store = InMemoryVersionStore()
    access_log = InMemoryAccessLog()
    svc = DocumentStoreService(
        document_store=doc_store,
        version_store=version_store,
        access_log=access_log,
    )
    vm = VersionManager(
        document_store=doc_store,
        version_store=version_store,
        access_log=access_log,
    )
    return svc, vm, access_log


@pytest.mark.asyncio
async def test_create_version_increments_number():
    svc, vm, _ = _make_components()
    doc = await svc.upload(
        name="doc.txt",
        category=DocumentCategory.KYC,
        content="original",
        entity_id="entity-001",
        uploaded_by="user-001",
        access_level=AccessLevel.INTERNAL,
    )
    v2 = await vm.create_version(doc.doc_id, "updated content", "Minor update", "user-001")
    assert v2.version_number == 2


@pytest.mark.asyncio
async def test_create_version_computes_hash():
    svc, vm, _ = _make_components()
    doc = await svc.upload(
        name="doc.txt",
        category=DocumentCategory.KYC,
        content="original",
        entity_id="entity-001",
        uploaded_by="user-001",
        access_level=AccessLevel.INTERNAL,
    )
    new_content = "updated content"
    expected_hash = hashlib.sha256(new_content.encode()).hexdigest()
    v2 = await vm.create_version(doc.doc_id, new_content, "Updated", "user-001")
    assert v2.content_hash == expected_hash


@pytest.mark.asyncio
async def test_create_multiple_versions():
    svc, vm, _ = _make_components()
    doc = await svc.upload(
        name="doc.txt",
        category=DocumentCategory.KYC,
        content="v1",
        entity_id="entity-001",
        uploaded_by="user-001",
        access_level=AccessLevel.INTERNAL,
    )
    await vm.create_version(doc.doc_id, "v2 content", "v2", "user-001")
    await vm.create_version(doc.doc_id, "v3 content", "v3", "user-001")
    versions = await vm.get_versions(doc.doc_id)
    assert len(versions) == 3
    assert [v.version_number for v in versions] == [1, 2, 3]


@pytest.mark.asyncio
async def test_get_versions_sorted():
    svc, vm, _ = _make_components()
    doc = await svc.upload(
        name="doc.txt",
        category=DocumentCategory.KYC,
        content="v1",
        entity_id="entity-001",
        uploaded_by="user-001",
        access_level=AccessLevel.INTERNAL,
    )
    await vm.create_version(doc.doc_id, "v2 content", "v2", "user-001")
    versions = await vm.get_versions(doc.doc_id)
    assert versions[0].version_number < versions[1].version_number


@pytest.mark.asyncio
async def test_get_latest_version_returns_highest():
    svc, vm, _ = _make_components()
    doc = await svc.upload(
        name="doc.txt",
        category=DocumentCategory.KYC,
        content="v1",
        entity_id="entity-001",
        uploaded_by="user-001",
        access_level=AccessLevel.INTERNAL,
    )
    await vm.create_version(doc.doc_id, "v2 content", "v2", "user-001")
    latest = await vm.get_latest_version(doc.doc_id)
    assert latest is not None
    assert latest.version_number == 2


@pytest.mark.asyncio
async def test_get_latest_version_returns_none_no_versions():
    _, vm, _ = _make_components()
    latest = await vm.get_latest_version("nonexistent-doc")
    assert latest is None


@pytest.mark.asyncio
async def test_rollback_creates_new_version():
    svc, vm, _ = _make_components()
    doc = await svc.upload(
        name="doc.txt",
        category=DocumentCategory.KYC,
        content="original",
        entity_id="entity-001",
        uploaded_by="user-001",
        access_level=AccessLevel.INTERNAL,
    )
    await vm.create_version(doc.doc_id, "v2 content", "v2", "user-001")
    rollback = await vm.rollback(doc.doc_id, version_number=1, actor="admin-001")
    assert rollback.version_number == 3
    assert rollback.change_note == "Rollback to v1"


@pytest.mark.asyncio
async def test_rollback_uses_target_content_hash():
    svc, vm, _ = _make_components()
    original_content = "original content"
    expected_hash = hashlib.sha256(original_content.encode()).hexdigest()
    doc = await svc.upload(
        name="doc.txt",
        category=DocumentCategory.KYC,
        content=original_content,
        entity_id="entity-001",
        uploaded_by="user-001",
        access_level=AccessLevel.INTERNAL,
    )
    await vm.create_version(doc.doc_id, "modified content", "modified", "user-001")
    rollback = await vm.rollback(doc.doc_id, version_number=1, actor="admin-001")
    assert rollback.content_hash == expected_hash


@pytest.mark.asyncio
async def test_rollback_nonexistent_version_raises():
    svc, vm, _ = _make_components()
    doc = await svc.upload(
        name="doc.txt",
        category=DocumentCategory.KYC,
        content="content",
        entity_id="entity-001",
        uploaded_by="user-001",
        access_level=AccessLevel.INTERNAL,
    )
    with pytest.raises(ValueError):
        await vm.rollback(doc.doc_id, version_number=99, actor="admin-001")


@pytest.mark.asyncio
async def test_create_version_logs_update_action():
    svc, vm, access_log = _make_components()
    doc = await svc.upload(
        name="doc.txt",
        category=DocumentCategory.KYC,
        content="content",
        entity_id="entity-001",
        uploaded_by="user-001",
        access_level=AccessLevel.INTERNAL,
    )
    await vm.create_version(doc.doc_id, "new content", "updated", "user-002")
    records = await access_log.list_access(doc.doc_id)
    update_records = [r for r in records if r.action == "UPDATE"]
    assert len(update_records) == 1


@pytest.mark.asyncio
async def test_rollback_logs_update_action():
    svc, vm, access_log = _make_components()
    doc = await svc.upload(
        name="doc.txt",
        category=DocumentCategory.KYC,
        content="original",
        entity_id="entity-001",
        uploaded_by="user-001",
        access_level=AccessLevel.INTERNAL,
    )
    await vm.create_version(doc.doc_id, "v2 content", "v2", "user-001")
    await vm.rollback(doc.doc_id, version_number=1, actor="admin-001")
    records = await access_log.list_access(doc.doc_id)
    update_records = [r for r in records if r.action == "UPDATE"]
    assert len(update_records) == 2  # create_version + rollback


@pytest.mark.asyncio
async def test_version_change_note_stored():
    svc, vm, _ = _make_components()
    doc = await svc.upload(
        name="doc.txt",
        category=DocumentCategory.KYC,
        content="content",
        entity_id="entity-001",
        uploaded_by="user-001",
        access_level=AccessLevel.INTERNAL,
    )
    v2 = await vm.create_version(doc.doc_id, "new content", "Fixed typos", "user-001")
    assert v2.change_note == "Fixed typos"


@pytest.mark.asyncio
async def test_version_created_by_stored():
    svc, vm, _ = _make_components()
    doc = await svc.upload(
        name="doc.txt",
        category=DocumentCategory.KYC,
        content="content",
        entity_id="entity-001",
        uploaded_by="user-001",
        access_level=AccessLevel.INTERNAL,
    )
    v2 = await vm.create_version(doc.doc_id, "new content", "Update", "user-007")
    assert v2.created_by == "user-007"


@pytest.mark.asyncio
async def test_get_versions_returns_empty_for_unknown_doc():
    _, vm, _ = _make_components()
    versions = await vm.get_versions("nonexistent-doc-id")
    assert versions == []
