"""
tests/test_audit_trail/test_search_engine.py
IL-AES-01 | Phase 40 | banxe-emi-stack — 18 tests
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from services.audit_trail.event_store import EventStore
from services.audit_trail.models import (
    AuditAction,
    EventCategory,
    EventSeverity,
    InMemoryChainPort,
    InMemoryEventStorePort,
    SearchQuery,
    SourceSystem,
)
from services.audit_trail.search_engine import SearchEngine


def _setup() -> tuple[EventStore, SearchEngine]:
    port = InMemoryEventStorePort()
    chain = InMemoryChainPort()
    store = EventStore(port, chain)
    engine = SearchEngine(port)
    return store, engine


def _add(
    store: EventStore,
    category: EventCategory,
    entity_id: str,
    actor_id: str = "u1",
    severity: EventSeverity = EventSeverity.INFO,
) -> None:
    store.append(
        category,
        severity,
        AuditAction.CREATE,
        "entity",
        entity_id,
        actor_id,
        {"info": "test"},
        SourceSystem.API,
    )


class TestSearch:
    def test_search_returns_dict(self) -> None:
        store, engine = _setup()
        result = engine.search(SearchQuery())
        assert "results" in result
        assert "total" in result

    def test_search_filter_by_category(self) -> None:
        store, engine = _setup()
        _add(store, EventCategory.AML, "e-aml")
        _add(store, EventCategory.PAYMENT, "e-pay")
        result = engine.search(SearchQuery(categories=[EventCategory.AML]))
        for e in result["results"]:
            assert e.category == EventCategory.AML

    def test_search_filter_by_entity_id(self) -> None:
        store, engine = _setup()
        _add(store, EventCategory.PAYMENT, "SPECIFIC-ENTITY")
        result = engine.search(SearchQuery(entity_id="SPECIFIC-ENTITY"))
        assert all(e.entity_id == "SPECIFIC-ENTITY" for e in result["results"])

    def test_search_filter_by_actor_id(self) -> None:
        store, engine = _setup()
        _add(store, EventCategory.AUTH, "e-1", actor_id="actor-SPECIAL")
        result = engine.search(SearchQuery(actor_id="actor-SPECIAL"))
        assert all(e.actor_id == "actor-SPECIAL" for e in result["results"])

    def test_search_filter_by_severity(self) -> None:
        store, engine = _setup()
        _add(store, EventCategory.AML, "e-1", severity=EventSeverity.WARNING)
        result = engine.search(SearchQuery(severity=EventSeverity.WARNING))
        assert all(e.severity == EventSeverity.WARNING for e in result["results"])

    def test_search_pagination_page_size(self) -> None:
        store, engine = _setup()
        for i in range(10):
            _add(store, EventCategory.ADMIN, f"e-{i}")
        result = engine.search(SearchQuery(page=1, page_size=3))
        assert len(result["results"]) <= 3

    def test_search_page_2(self) -> None:
        store, engine = _setup()
        for i in range(10):
            _add(store, EventCategory.ADMIN, f"pg-{i}")
        result1 = engine.search(SearchQuery(page=1, page_size=3))
        result2 = engine.search(SearchQuery(page=2, page_size=3))
        ids1 = {e.id for e in result1["results"]}
        ids2 = {e.id for e in result2["results"]}
        assert ids1.isdisjoint(ids2)

    def test_search_returns_total_count(self) -> None:
        store, engine = _setup()
        _add(store, EventCategory.PAYMENT, "pay-1")
        _add(store, EventCategory.PAYMENT, "pay-2")
        result = engine.search(SearchQuery(categories=[EventCategory.PAYMENT]))
        assert result["total"] >= 2

    def test_search_time_range_filter(self) -> None:
        _, engine = _setup()
        now = datetime.now(UTC)
        far_future = now + timedelta(days=365)
        result = engine.search(
            SearchQuery(from_ts=far_future, to_ts=far_future + timedelta(hours=1))
        )
        assert result["total"] == 0


class TestSearchByActor:
    def test_search_by_actor(self) -> None:
        store, engine = _setup()
        _add(store, EventCategory.AUTH, "e-1", actor_id="ACTOR-X")
        _add(store, EventCategory.AUTH, "e-2", actor_id="ACTOR-X")
        events = engine.search_by_actor("ACTOR-X")
        assert all(e.actor_id == "ACTOR-X" for e in events)

    def test_search_by_actor_limit(self) -> None:
        store, engine = _setup()
        for i in range(10):
            _add(store, EventCategory.AUTH, f"a-{i}", actor_id="ACTOR-Y")
        events = engine.search_by_actor("ACTOR-Y", limit=5)
        assert len(events) <= 5


class TestSearchByEntity:
    def test_search_by_entity(self) -> None:
        store, engine = _setup()
        _add(store, EventCategory.PAYMENT, "ENT-Z")
        events = engine.search_by_entity("ENT-Z")
        assert all(e.entity_id == "ENT-Z" for e in events)


class TestFullTextSearch:
    def test_full_text_match(self) -> None:
        store, engine = _setup()
        store.append(
            EventCategory.PAYMENT,
            EventSeverity.INFO,
            AuditAction.CREATE,
            "pay",
            "ft-1",
            "u1",
            {"note": "searchable text here"},
            SourceSystem.API,
        )
        results = engine.full_text_search("searchable")
        assert len(results) >= 1

    def test_full_text_case_insensitive(self) -> None:
        store, engine = _setup()
        store.append(
            EventCategory.AML,
            EventSeverity.WARNING,
            AuditAction.ESCALATE,
            "tx",
            "ft-2",
            "agent",
            {"reason": "THRESHOLD"},
            SourceSystem.AGENT,
        )
        results = engine.full_text_search("threshold")
        assert len(results) >= 1

    def test_full_text_no_match(self) -> None:
        _, engine = _setup()
        results = engine.full_text_search("xyzzynonexistent12345")
        assert results == []


class TestSeveritySummary:
    def test_severity_summary_returns_dict(self) -> None:
        _, engine = _setup()
        summary = engine.get_severity_summary()
        assert isinstance(summary, dict)

    def test_severity_summary_has_counts(self) -> None:
        store, engine = _setup()
        _add(store, EventCategory.PAYMENT, "e-1", severity=EventSeverity.INFO)
        summary = engine.get_severity_summary()
        assert summary.get("INFO", 0) >= 1
