"""
tests/test_audit_trail/test_event_replayer.py
IL-AES-01 | Phase 40 | banxe-emi-stack — 18 tests
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from services.audit_trail.event_replayer import EventReplayer
from services.audit_trail.event_store import EventStore
from services.audit_trail.models import (
    AuditAction,
    EventCategory,
    EventSeverity,
    InMemoryChainPort,
    InMemoryEventStorePort,
    SourceSystem,
)


def _store_with_events() -> tuple[EventStore, InMemoryEventStorePort]:
    port = InMemoryEventStorePort()
    chain = InMemoryChainPort()
    store = EventStore(port, chain)
    return store, port


def _replayer(store: EventStore) -> EventReplayer:
    return EventReplayer(store._events)


def _ts(offset_seconds: int = 0) -> datetime:
    return datetime.now(UTC) + timedelta(seconds=offset_seconds)


class TestReplayEntity:
    def test_replay_returns_events_in_range(self) -> None:
        store, _ = _store_with_events()
        now = datetime.now(UTC)
        store.append(
            EventCategory.PAYMENT,
            EventSeverity.INFO,
            AuditAction.CREATE,
            "pay",
            "E-1",
            "u1",
            {},
            SourceSystem.API,
        )
        replayer = _replayer(store)
        events = replayer.replay_entity(
            "E-1", now - timedelta(minutes=1), now + timedelta(minutes=1)
        )
        assert len(events) >= 1

    def test_replay_excludes_out_of_range(self) -> None:
        store, _ = _store_with_events()
        now = datetime.now(UTC)
        store.append(
            EventCategory.PAYMENT,
            EventSeverity.INFO,
            AuditAction.CREATE,
            "pay",
            "E-2",
            "u1",
            {},
            SourceSystem.API,
        )
        replayer = _replayer(store)
        far_future = now + timedelta(hours=10)
        events = replayer.replay_entity("E-2", far_future, far_future + timedelta(hours=1))
        assert len(events) == 0

    def test_replay_returns_ascending_order(self) -> None:
        store, _ = _store_with_events()
        now = datetime.now(UTC)
        for _ in range(3):
            store.append(
                EventCategory.PAYMENT,
                EventSeverity.INFO,
                AuditAction.CREATE,
                "pay",
                "E-ORDER",
                "u1",
                {},
                SourceSystem.API,
            )
        replayer = _replayer(store)
        events = replayer.replay_entity(
            "E-ORDER", now - timedelta(minutes=1), now + timedelta(minutes=1)
        )
        timestamps = [e.timestamp for e in events]
        assert timestamps == sorted(timestamps)


class TestReplayCategory:
    def test_replay_category_filters(self) -> None:
        store, _ = _store_with_events()
        now = datetime.now(UTC)
        store.append(
            EventCategory.AML,
            EventSeverity.WARNING,
            AuditAction.ESCALATE,
            "tx",
            "T-1",
            "agent",
            {},
            SourceSystem.AGENT,
        )
        store.append(
            EventCategory.PAYMENT,
            EventSeverity.INFO,
            AuditAction.CREATE,
            "pay",
            "P-1",
            "u1",
            {},
            SourceSystem.API,
        )
        replayer = _replayer(store)
        events = replayer.replay_category(
            EventCategory.AML, now - timedelta(minutes=1), now + timedelta(minutes=1)
        )
        assert all(e.category == EventCategory.AML for e in events)

    def test_replay_category_empty_when_no_match(self) -> None:
        store, _ = _store_with_events()
        now = datetime.now(UTC)
        replayer = _replayer(store)
        future = now + timedelta(days=365)
        events = replayer.replay_category(
            EventCategory.CUSTOMER, future, future + timedelta(hours=1)
        )
        assert events == []


class TestReconstructState:
    def test_reconstruct_returns_dict(self) -> None:
        store, _ = _store_with_events()
        now = datetime.now(UTC)
        store.append(
            EventCategory.PAYMENT,
            EventSeverity.INFO,
            AuditAction.CREATE,
            "pay",
            "STATE-1",
            "u1",
            {},
            SourceSystem.API,
        )
        replayer = _replayer(store)
        state = replayer.reconstruct_state("STATE-1", now + timedelta(minutes=1))
        assert isinstance(state, dict)

    def test_reconstruct_has_event_count(self) -> None:
        store, _ = _store_with_events()
        now = datetime.now(UTC)
        store.append(
            EventCategory.PAYMENT,
            EventSeverity.INFO,
            AuditAction.CREATE,
            "pay",
            "STATE-2",
            "u1",
            {},
            SourceSystem.API,
        )
        replayer = _replayer(store)
        state = replayer.reconstruct_state("STATE-2", now + timedelta(minutes=1))
        assert state["event_count"] >= 1

    def test_reconstruct_empty_entity(self) -> None:
        store, _ = _store_with_events()
        replayer = _replayer(store)
        state = replayer.reconstruct_state("UNKNOWN", datetime.now(UTC))
        assert state["event_count"] == 0

    def test_reconstruct_last_actor(self) -> None:
        store, _ = _store_with_events()
        now = datetime.now(UTC)
        store.append(
            EventCategory.AUTH,
            EventSeverity.INFO,
            AuditAction.UPDATE,
            "session",
            "SESS-1",
            "actor-X",
            {},
            SourceSystem.API,
        )
        replayer = _replayer(store)
        state = replayer.reconstruct_state("SESS-1", now + timedelta(minutes=1))
        assert state["last_actor"] == "actor-X"


class TestPointInTimeSnapshot:
    def test_snapshot_wraps_state(self) -> None:
        store, _ = _store_with_events()
        now = datetime.now(UTC)
        store.append(
            EventCategory.ADMIN,
            EventSeverity.INFO,
            AuditAction.CREATE,
            "config",
            "CFG-SNAP",
            "admin",
            {},
            SourceSystem.API,
        )
        replayer = _replayer(store)
        snap = replayer.point_in_time_snapshot("CFG-SNAP", now + timedelta(minutes=1))
        assert snap["snapshot_type"] == "point_in_time"
        assert "state" in snap

    def test_snapshot_includes_as_of(self) -> None:
        store, _ = _store_with_events()
        now = datetime.now(UTC)
        replayer = _replayer(store)
        snap = replayer.point_in_time_snapshot("any", now)
        assert "as_of" in snap


class TestGetEventTimeline:
    def test_timeline_returns_list(self) -> None:
        store, _ = _store_with_events()
        store.append(
            EventCategory.PAYMENT,
            EventSeverity.INFO,
            AuditAction.CREATE,
            "pay",
            "TL-1",
            "u1",
            {},
            SourceSystem.API,
        )
        replayer = _replayer(store)
        timeline = replayer.get_event_timeline("TL-1")
        assert isinstance(timeline, list)

    def test_timeline_has_timestamp_field(self) -> None:
        store, _ = _store_with_events()
        store.append(
            EventCategory.PAYMENT,
            EventSeverity.INFO,
            AuditAction.CREATE,
            "pay",
            "TL-2",
            "u1",
            {},
            SourceSystem.API,
        )
        replayer = _replayer(store)
        timeline = replayer.get_event_timeline("TL-2")
        assert len(timeline) >= 1
        assert "timestamp" in timeline[0]
        assert "action" in timeline[0]
        assert "actor_id" in timeline[0]
        assert "severity" in timeline[0]

    def test_timeline_empty_for_unknown(self) -> None:
        store, _ = _store_with_events()
        replayer = _replayer(store)
        timeline = replayer.get_event_timeline("UNKNOWN-ENTITY")
        assert timeline == []
