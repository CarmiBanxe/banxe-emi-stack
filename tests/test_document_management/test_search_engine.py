"""
tests/test_document_management/test_search_engine.py — SearchEngine tests
IL-DMS-01 | Phase 24 | banxe-emi-stack

12+ tests: index + search, keyword match, category filter, entity_id filter.
"""

from __future__ import annotations

from datetime import UTC, datetime
import uuid

import pytest

from services.document_management.models import (
    AccessLevel,
    Document,
    DocumentCategory,
    DocumentStatus,
    InMemoryDocumentStore,
    InMemorySearchIndex,
)
from services.document_management.search_engine import SearchEngine


def _now() -> datetime:
    return datetime.now(UTC)


def _make_engine():
    doc_store = InMemoryDocumentStore()
    search_index = InMemorySearchIndex()
    engine = SearchEngine(search_index=search_index, document_store=doc_store)
    return engine, doc_store


def _make_doc(
    name: str,
    category: DocumentCategory = DocumentCategory.KYC,
    entity_id: str = "entity-001",
    tags: tuple[str, ...] = (),
) -> Document:
    return Document(
        doc_id=str(uuid.uuid4()),
        name=name,
        category=category,
        content_hash="hash123",
        size_bytes=100,
        mime_type="text/plain",
        status=DocumentStatus.ACTIVE,
        access_level=AccessLevel.INTERNAL,
        entity_id=entity_id,
        uploaded_by="user-001",
        created_at=_now(),
        tags=tags,
    )


@pytest.mark.asyncio
async def test_index_and_search_by_name():
    engine, doc_store = _make_engine()
    doc = _make_doc("passport verification kyc")
    await doc_store.save(doc)
    await engine.index_document(doc, "full content")
    results = await engine.search("passport")
    assert len(results) == 1
    assert results[0].doc_id == doc.doc_id


@pytest.mark.asyncio
async def test_search_no_match_returns_empty():
    engine, doc_store = _make_engine()
    doc = _make_doc("kyc passport document")
    await doc_store.save(doc)
    await engine.index_document(doc, "content")
    results = await engine.search("contract")
    assert results == []


@pytest.mark.asyncio
async def test_search_tag_match_lower_score():
    engine, doc_store = _make_engine()
    doc = _make_doc("document name", tags=("kyc", "passport"))
    await doc_store.save(doc)
    await engine.index_document(doc, "content")
    results = await engine.search("passport")
    assert len(results) == 1
    assert results[0].relevance_score == 0.5


@pytest.mark.asyncio
async def test_search_name_match_higher_score():
    engine, doc_store = _make_engine()
    doc = _make_doc("passport document")
    await doc_store.save(doc)
    await engine.index_document(doc, "content")
    results = await engine.search("passport")
    assert results[0].relevance_score == 1.0


@pytest.mark.asyncio
async def test_search_category_filter():
    engine, doc_store = _make_engine()
    kyc_doc = _make_doc("kyc document", category=DocumentCategory.KYC)
    aml_doc = _make_doc("aml document", category=DocumentCategory.AML)
    await doc_store.save(kyc_doc)
    await doc_store.save(aml_doc)
    await engine.index_document(kyc_doc, "content")
    await engine.index_document(aml_doc, "content")

    results = await engine.search("document", category=DocumentCategory.KYC)
    assert len(results) == 1
    assert results[0].category == DocumentCategory.KYC


@pytest.mark.asyncio
async def test_search_entity_filter():
    engine, doc_store = _make_engine()
    doc1 = _make_doc("test document", entity_id="entity-001")
    doc2 = _make_doc("test document", entity_id="entity-002")
    await doc_store.save(doc1)
    await doc_store.save(doc2)
    await engine.index_document(doc1, "content")
    await engine.index_document(doc2, "content")

    results = await engine.search("test", entity_id="entity-001")
    assert len(results) == 1
    assert results[0].doc_id == doc1.doc_id


@pytest.mark.asyncio
async def test_search_sorted_by_relevance_descending():
    engine, doc_store = _make_engine()
    # name match score=1.0
    name_doc = _make_doc("kyc name match")
    # tag match score=0.5
    tag_doc = _make_doc("other document", tags=("kyc",))
    await doc_store.save(name_doc)
    await doc_store.save(tag_doc)
    await engine.index_document(name_doc, "content")
    await engine.index_document(tag_doc, "content")

    results = await engine.search("kyc")
    assert len(results) == 2
    assert results[0].relevance_score >= results[1].relevance_score


@pytest.mark.asyncio
async def test_reindex_all_returns_count():
    engine, doc_store = _make_engine()
    for i in range(3):
        doc = _make_doc(f"doc {i}", entity_id="entity-001")
        await doc_store.save(doc)

    count = await engine.reindex_all("entity-001")
    assert count == 3


@pytest.mark.asyncio
async def test_reindex_all_makes_docs_searchable():
    engine, doc_store = _make_engine()
    doc = _make_doc("passport doc", entity_id="entity-001")
    await doc_store.save(doc)
    # Index via reindex_all
    await engine.reindex_all("entity-001")
    results = await engine.search("passport")
    assert len(results) == 1


@pytest.mark.asyncio
async def test_reindex_all_entity_isolation():
    engine, doc_store = _make_engine()
    doc1 = _make_doc("entity1 doc", entity_id="entity-001")
    doc2 = _make_doc("entity2 doc", entity_id="entity-002")
    await doc_store.save(doc1)
    await doc_store.save(doc2)

    count = await engine.reindex_all("entity-001")
    assert count == 1


@pytest.mark.asyncio
async def test_search_result_contains_snippet():
    engine, doc_store = _make_engine()
    doc = _make_doc("passport kyc document")
    await doc_store.save(doc)
    await engine.index_document(doc, "content")
    results = await engine.search("passport")
    assert results[0].snippet is not None
    assert len(results[0].snippet) > 0


@pytest.mark.asyncio
async def test_search_multiple_query_words():
    engine, doc_store = _make_engine()
    doc = _make_doc("passport kyc verification document")
    await doc_store.save(doc)
    await engine.index_document(doc, "content")
    results = await engine.search("passport kyc")
    assert len(results) == 1
