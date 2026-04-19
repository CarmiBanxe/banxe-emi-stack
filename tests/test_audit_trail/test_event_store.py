"""
tests/test_audit_trail/test_event_store.py
IL-AES-01 | Phase 40 | banxe-emi-stack — 20 tests
"""

from __future__ import annotations

import hashlib
import json

from services.audit_trail.event_store import EventStore, _compute_chain_hash
from services.audit_trail.models import (
    AuditAction,
    AuditEvent,
    EventCategory,
    EventSeverity,
    InMemoryChainPort,
    InMemoryEventStorePort,
    SourceSystem,
)


def _store() -> EventStore:
    return EventStore(InMemoryEventStorePort(), InMemoryChainPort())


def _append_one(store: EventStore, entity_id: str = "e-1") -> AuditEvent:
    return store.append(
        category=EventCategory.PAYMENT,
        severity=EventSeverity.INFO,
        action=AuditAction.CREATE,
        entity_type="payment",
        entity_id=entity_id,
        actor_id="user-1",
        details={"amount": "100.00"},
        source=SourceSystem.API,
    )


class TestAppend:
    def test_append_returns_event(self) -> None:
        store = _store()
        event = _append_one(store)
        assert event.id is not None

    def test_append_chain_hash_not_empty(self) -> None:
        store = _store()
        event = _append_one(store)
        assert len(event.chain_hash) == 64

    def test_first_event_prev_hash_none(self) -> None:
        store = _store()
        event = _append_one(store)
        assert event.prev_hash is None

    def test_second_event_prev_hash_set(self) -> None:
        store = _store()
        first = _append_one(store, "e-1")
        second = _append_one(store, "e-2")
        assert second.prev_hash == first.chain_hash

    def test_chain_hash_is_sha256(self) -> None:
        store = _store()
        event = _append_one(store)
        recomputed = _compute_chain_hash(
            {
                "category": event.category.value,
                "severity": event.severity.value,
                "action": event.action.value,
                "entity_type": event.entity_type,
                "entity_id": event.entity_id,
                "actor_id": event.actor_id,
                "timestamp": event.timestamp.isoformat(),
            },
            event.prev_hash,
        )
        assert event.chain_hash == recomputed

    def test_chain_hash_uses_genesis_for_first(self) -> None:
        store = _store()
        event = _append_one(store)
        event_data = {
            "category": event.category.value,
            "severity": event.severity.value,
            "action": event.action.value,
            "entity_type": event.entity_type,
            "entity_id": event.entity_id,
            "actor_id": event.actor_id,
            "timestamp": event.timestamp.isoformat(),
        }
        payload = json.dumps(event_data, sort_keys=True, default=str) + "GENESIS"
        expected = hashlib.sha256(payload.encode()).hexdigest()
        assert event.chain_hash == expected

    def test_append_updates_chain_head(self) -> None:
        store = _store()
        event = _append_one(store)
        head = store.get_chain_head(SourceSystem.API)
        assert head == event.chain_hash


class TestGetEvent:
    def test_get_existing_event(self) -> None:
        store = _store()
        event = _append_one(store)
        fetched = store.get_event(event.id)
        assert fetched is not None
        assert fetched.id == event.id

    def test_get_nonexistent_returns_none(self) -> None:
        store = _store()
        assert store.get_event("nonexistent-id") is None

    def test_get_returns_correct_category(self) -> None:
        store = _store()
        event = store.append(
            EventCategory.AML,
            EventSeverity.WARNING,
            AuditAction.ESCALATE,
            "tx",
            "TX-001",
            "agent",
            {},
            SourceSystem.AGENT,
        )
        fetched = store.get_event(event.id)
        assert fetched.category == EventCategory.AML


class TestListByEntity:
    def test_list_by_entity_returns_events(self) -> None:
        store = _store()
        _append_one(store, "entity-A")
        _append_one(store, "entity-A")
        events = store.list_by_entity("entity-A", 10)
        assert len(events) == 2

    def test_list_by_entity_filters_correctly(self) -> None:
        store = _store()
        _append_one(store, "entity-A")
        _append_one(store, "entity-B")
        events = store.list_by_entity("entity-A", 10)
        assert all(e.entity_id == "entity-A" for e in events)

    def test_list_by_entity_respects_limit(self) -> None:
        store = _store()
        for _ in range(5):
            _append_one(store, "entity-C")
        events = store.list_by_entity("entity-C", 3)
        assert len(events) <= 3


class TestBulkAppend:
    def test_bulk_append_returns_count(self) -> None:
        store = _store()
        data = [
            {
                "category": "PAYMENT",
                "action": "CREATE",
                "entity_id": "e-1",
                "entity_type": "payment",
                "actor_id": "u1",
                "details": {},
            },
            {
                "category": "AUTH",
                "action": "READ",
                "entity_id": "e-2",
                "entity_type": "session",
                "actor_id": "u2",
                "details": {},
            },
        ]
        count = store.bulk_append(data)
        assert count == 2

    def test_bulk_append_empty_returns_zero(self) -> None:
        store = _store()
        assert store.bulk_append([]) == 0

    def test_bulk_append_events_stored(self) -> None:
        store = _store()
        data = [
            {
                "category": "ADMIN",
                "action": "UPDATE",
                "entity_id": "cfg-1",
                "entity_type": "config",
                "actor_id": "admin",
                "details": {"key": "val"},
            },
        ]
        store.bulk_append(data)
        events = store.list_by_entity("cfg-1", 10)
        assert len(events) == 1


class TestAppendOnly:
    def test_no_delete_method(self) -> None:
        store = _store()
        assert not hasattr(store, "delete")
        assert not hasattr(store, "delete_event")

    def test_no_update_method(self) -> None:
        store = _store()
        assert not hasattr(store, "update")
        assert not hasattr(store, "update_event")
