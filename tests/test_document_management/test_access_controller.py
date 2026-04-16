"""
tests/test_document_management/test_access_controller.py — AccessController tests
IL-DMS-01 | Phase 24 | banxe-emi-stack

14+ tests: role-based access (admin=all, customer=PUBLIC only), access_denied log, can_delete roles.
"""

from __future__ import annotations

from datetime import UTC, datetime
import uuid

import pytest

from services.document_management.access_controller import AccessController
from services.document_management.models import (
    AccessLevel,
    Document,
    DocumentCategory,
    DocumentStatus,
    InMemoryAccessLog,
    InMemoryDocumentStore,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _make_controller():
    doc_store = InMemoryDocumentStore()
    access_log = InMemoryAccessLog()
    controller = AccessController(access_log=access_log, document_store=doc_store)
    return controller, doc_store, access_log


async def _save_doc(
    doc_store: InMemoryDocumentStore,
    access_level: AccessLevel,
    entity_id: str = "entity-001",
) -> Document:
    doc = Document(
        doc_id=str(uuid.uuid4()),
        name="test.pdf",
        category=DocumentCategory.KYC,
        content_hash="hash123",
        size_bytes=100,
        mime_type="text/plain",
        status=DocumentStatus.ACTIVE,
        access_level=access_level,
        entity_id=entity_id,
        uploaded_by="user-001",
        created_at=_now(),
    )
    await doc_store.save(doc)
    return doc


@pytest.mark.asyncio
async def test_admin_accesses_restricted():
    controller, doc_store, _ = _make_controller()
    doc = await _save_doc(doc_store, AccessLevel.RESTRICTED)
    allowed = await controller.check_access(doc.doc_id, "admin", "VIEW")
    assert allowed is True


@pytest.mark.asyncio
async def test_admin_accesses_confidential():
    controller, doc_store, _ = _make_controller()
    doc = await _save_doc(doc_store, AccessLevel.CONFIDENTIAL)
    allowed = await controller.check_access(doc.doc_id, "admin", "VIEW")
    assert allowed is True


@pytest.mark.asyncio
async def test_customer_accesses_public():
    controller, doc_store, _ = _make_controller()
    doc = await _save_doc(doc_store, AccessLevel.PUBLIC)
    allowed = await controller.check_access(doc.doc_id, "customer", "VIEW")
    assert allowed is True


@pytest.mark.asyncio
async def test_customer_denied_internal():
    controller, doc_store, _ = _make_controller()
    doc = await _save_doc(doc_store, AccessLevel.INTERNAL)
    allowed = await controller.check_access(doc.doc_id, "customer", "VIEW")
    assert allowed is False


@pytest.mark.asyncio
async def test_customer_denied_confidential():
    controller, doc_store, _ = _make_controller()
    doc = await _save_doc(doc_store, AccessLevel.CONFIDENTIAL)
    allowed = await controller.check_access(doc.doc_id, "customer", "VIEW")
    assert allowed is False


@pytest.mark.asyncio
async def test_customer_denied_restricted():
    controller, doc_store, _ = _make_controller()
    doc = await _save_doc(doc_store, AccessLevel.RESTRICTED)
    allowed = await controller.check_access(doc.doc_id, "customer", "VIEW")
    assert allowed is False


@pytest.mark.asyncio
async def test_support_accesses_internal():
    controller, doc_store, _ = _make_controller()
    doc = await _save_doc(doc_store, AccessLevel.INTERNAL)
    allowed = await controller.check_access(doc.doc_id, "support", "VIEW")
    assert allowed is True


@pytest.mark.asyncio
async def test_support_denied_confidential():
    controller, doc_store, _ = _make_controller()
    doc = await _save_doc(doc_store, AccessLevel.CONFIDENTIAL)
    allowed = await controller.check_access(doc.doc_id, "support", "VIEW")
    assert allowed is False


@pytest.mark.asyncio
async def test_analyst_accesses_confidential():
    controller, doc_store, _ = _make_controller()
    doc = await _save_doc(doc_store, AccessLevel.CONFIDENTIAL)
    allowed = await controller.check_access(doc.doc_id, "analyst", "VIEW")
    assert allowed is True


@pytest.mark.asyncio
async def test_analyst_denied_restricted():
    controller, doc_store, _ = _make_controller()
    doc = await _save_doc(doc_store, AccessLevel.RESTRICTED)
    allowed = await controller.check_access(doc.doc_id, "analyst", "VIEW")
    assert allowed is False


@pytest.mark.asyncio
async def test_access_denied_logged():
    controller, doc_store, access_log = _make_controller()
    doc = await _save_doc(doc_store, AccessLevel.RESTRICTED)
    await controller.check_access(doc.doc_id, "customer", "VIEW")
    records = await access_log.list_access(doc.doc_id)
    denied_records = [r for r in records if r.action == "ACCESS_DENIED"]
    assert len(denied_records) == 1


@pytest.mark.asyncio
async def test_access_allowed_logged_with_action():
    controller, doc_store, access_log = _make_controller()
    doc = await _save_doc(doc_store, AccessLevel.PUBLIC)
    await controller.check_access(doc.doc_id, "customer", "VIEW")
    records = await access_log.list_access(doc.doc_id)
    view_records = [r for r in records if r.action == "VIEW"]
    assert len(view_records) == 1


@pytest.mark.asyncio
async def test_can_delete_admin():
    controller, _, _ = _make_controller()
    assert await controller.can_delete("admin") is True


@pytest.mark.asyncio
async def test_can_delete_compliance_officer():
    controller, _, _ = _make_controller()
    assert await controller.can_delete("compliance_officer") is True


@pytest.mark.asyncio
async def test_cannot_delete_analyst():
    controller, _, _ = _make_controller()
    assert await controller.can_delete("analyst") is False


@pytest.mark.asyncio
async def test_cannot_delete_support():
    controller, _, _ = _make_controller()
    assert await controller.can_delete("support") is False


@pytest.mark.asyncio
async def test_cannot_delete_customer():
    controller, _, _ = _make_controller()
    assert await controller.can_delete("customer") is False


@pytest.mark.asyncio
async def test_cannot_delete_mlro():
    controller, _, _ = _make_controller()
    assert await controller.can_delete("mlro") is False


@pytest.mark.asyncio
async def test_check_access_nonexistent_doc_returns_false():
    controller, _, _ = _make_controller()
    allowed = await controller.check_access("nonexistent-id", "admin", "VIEW")
    assert allowed is False


@pytest.mark.asyncio
async def test_get_access_log_returns_records():
    controller, doc_store, _ = _make_controller()
    doc = await _save_doc(doc_store, AccessLevel.INTERNAL)
    await controller.check_access(doc.doc_id, "admin", "VIEW")
    log = await controller.get_access_log(doc.doc_id)
    assert len(log) == 1


@pytest.mark.asyncio
async def test_compliance_officer_accesses_restricted():
    controller, doc_store, _ = _make_controller()
    doc = await _save_doc(doc_store, AccessLevel.RESTRICTED)
    allowed = await controller.check_access(doc.doc_id, "compliance_officer", "VIEW")
    assert allowed is True


@pytest.mark.asyncio
async def test_mlro_accesses_restricted():
    controller, doc_store, _ = _make_controller()
    doc = await _save_doc(doc_store, AccessLevel.RESTRICTED)
    allowed = await controller.check_access(doc.doc_id, "mlro", "VIEW")
    assert allowed is True
