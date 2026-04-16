"""
tests/test_document_management/test_document_agent.py — DocumentAgent tests
IL-DMS-01 | Phase 24 | banxe-emi-stack

12+ tests: upload+get+search flow, delete always HITL_REQUIRED, retention check.
"""

from __future__ import annotations

import pytest

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


def _make_agent():
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


@pytest.mark.asyncio
async def test_upload_document_returns_dict():
    agent = _make_agent()
    result = await agent.upload_document(
        name="kyc-passport.pdf",
        category="KYC",
        content="passport content",
        entity_id="entity-001",
        uploaded_by="user-001",
        role="admin",
        access_level="INTERNAL",
    )
    assert "doc_id" in result
    assert result["name"] == "kyc-passport.pdf"
    assert result["status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_upload_document_with_tags():
    agent = _make_agent()
    result = await agent.upload_document(
        name="doc.pdf",
        category="KYC",
        content="content",
        entity_id="entity-001",
        uploaded_by="user-001",
        role="admin",
        tags=["kyc", "passport"],
    )
    assert "kyc" in result["tags"]


@pytest.mark.asyncio
async def test_get_document_with_access():
    agent = _make_agent()
    uploaded = await agent.upload_document(
        name="internal.pdf",
        category="KYC",
        content="content",
        entity_id="entity-001",
        uploaded_by="user-001",
        role="admin",
        access_level="INTERNAL",
    )
    doc = await agent.get_document(
        doc_id=uploaded["doc_id"],
        accessed_by="user-002",
        role="admin",
    )
    assert doc is not None
    assert doc["doc_id"] == uploaded["doc_id"]


@pytest.mark.asyncio
async def test_get_document_access_denied_returns_none():
    agent = _make_agent()
    uploaded = await agent.upload_document(
        name="restricted.pdf",
        category="KYC",
        content="content",
        entity_id="entity-001",
        uploaded_by="user-001",
        role="admin",
        access_level="RESTRICTED",
    )
    doc = await agent.get_document(
        doc_id=uploaded["doc_id"],
        accessed_by="customer-001",
        role="customer",
    )
    assert doc is None


@pytest.mark.asyncio
async def test_get_document_not_found_returns_none():
    agent = _make_agent()
    doc = await agent.get_document(
        doc_id="nonexistent-id",
        accessed_by="user-001",
        role="admin",
    )
    assert doc is None


@pytest.mark.asyncio
async def test_search_documents_returns_results():
    agent = _make_agent()
    await agent.upload_document(
        name="passport kyc document",
        category="KYC",
        content="passport content",
        entity_id="entity-001",
        uploaded_by="user-001",
        role="admin",
    )
    results = await agent.search_documents("passport")
    assert len(results) == 1
    assert results[0]["name"] == "passport kyc document"


@pytest.mark.asyncio
async def test_search_documents_with_category_filter():
    agent = _make_agent()
    await agent.upload_document(
        name="kyc doc",
        category="KYC",
        content="content",
        entity_id="entity-001",
        uploaded_by="user-001",
        role="admin",
    )
    await agent.upload_document(
        name="aml doc",
        category="AML",
        content="content",
        entity_id="entity-001",
        uploaded_by="user-001",
        role="admin",
    )
    results = await agent.search_documents("doc", category="KYC")
    assert len(results) == 1
    assert results[0]["category"] == "KYC"


@pytest.mark.asyncio
async def test_get_versions_returns_history():
    agent = _make_agent()
    uploaded = await agent.upload_document(
        name="doc.txt",
        category="KYC",
        content="v1 content",
        entity_id="entity-001",
        uploaded_by="user-001",
        role="admin",
    )
    versions = await agent.get_versions(uploaded["doc_id"])
    assert len(versions) == 1
    assert versions[0]["version_number"] == 1


@pytest.mark.asyncio
async def test_delete_document_always_hitl_required():
    agent = _make_agent()
    uploaded = await agent.upload_document(
        name="doc.pdf",
        category="KYC",
        content="content",
        entity_id="entity-001",
        uploaded_by="user-001",
        role="admin",
    )
    result = await agent.delete_document(
        doc_id=uploaded["doc_id"],
        actor="admin-001",
        role="admin",
    )
    assert result["status"] == "HITL_REQUIRED"
    assert "Compliance Officer" in result["reason"]


@pytest.mark.asyncio
async def test_delete_document_hitl_for_any_role():
    agent = _make_agent()
    for role in ["admin", "compliance_officer", "customer", "support"]:
        result = await agent.delete_document(
            doc_id="any-doc-id",
            actor="user-001",
            role=role,
        )
        assert result["status"] == "HITL_REQUIRED"


@pytest.mark.asyncio
async def test_check_retention_status_returns_list():
    agent = _make_agent()
    status = await agent.check_retention_status("entity-001")
    assert isinstance(status, list)


@pytest.mark.asyncio
async def test_upload_document_content_hash_in_response():
    import hashlib

    agent = _make_agent()
    content = "unique content for hash test"
    expected_hash = hashlib.sha256(content.encode()).hexdigest()
    result = await agent.upload_document(
        name="hash-test.txt",
        category="KYC",
        content=content,
        entity_id="entity-001",
        uploaded_by="user-001",
        role="admin",
    )
    assert result["content_hash"] == expected_hash
