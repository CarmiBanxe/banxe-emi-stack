"""
services/audit_trail/event_replayer.py
IL-AES-01 | Phase 40 | banxe-emi-stack

EventReplayer — temporal query and state reconstruction for audit events.
Supports point-in-time snapshots and event timeline views.
"""

from __future__ import annotations

from datetime import datetime

from services.audit_trail.models import (
    AuditEvent,
    EventCategory,
    EventStorePort,
    InMemoryEventStorePort,
)


class EventReplayer:
    """Replays audit events for state reconstruction and temporal queries."""

    def __init__(self, event_port: EventStorePort | None = None) -> None:
        self._events: EventStorePort = event_port or InMemoryEventStorePort()

    def _all_events(self) -> list[AuditEvent]:
        """Get all events from store (using list_by_entity with wildcard via adapter)."""
        if hasattr(self._events, "list_all"):
            return self._events.list_all()  # type: ignore[attr-defined]
        return []

    def replay_entity(
        self,
        entity_id: str,
        from_ts: datetime,
        to_ts: datetime,
    ) -> list[AuditEvent]:
        """Return all events for entity in time range, ascending order."""
        events = self._events.list_by_entity(entity_id, limit=10000)
        filtered = [e for e in events if from_ts <= e.timestamp <= to_ts]
        return sorted(filtered, key=lambda e: e.timestamp)

    def replay_category(
        self,
        category: EventCategory,
        from_ts: datetime,
        to_ts: datetime,
    ) -> list[AuditEvent]:
        """Return all events for category in time range, ascending order."""
        all_events = self._all_events()
        filtered = [
            e for e in all_events if e.category == category and from_ts <= e.timestamp <= to_ts
        ]
        return sorted(filtered, key=lambda e: e.timestamp)

    def reconstruct_state(self, entity_id: str, as_of: datetime) -> dict:
        """Fold events up to as_of into state dict."""
        events = self._events.list_by_entity(entity_id, limit=10000)
        relevant = sorted(
            [e for e in events if e.timestamp <= as_of],
            key=lambda e: e.timestamp,
        )
        if not relevant:
            return {"entity_id": entity_id, "event_count": 0, "as_of": as_of.isoformat()}
        last = relevant[-1]
        return {
            "entity_id": entity_id,
            "action": last.action.value,
            "last_actor": last.actor_id,
            "event_count": len(relevant),
            "latest_ts": last.timestamp.isoformat(),
            "as_of": as_of.isoformat(),
        }

    def point_in_time_snapshot(self, entity_id: str, as_of: datetime) -> dict:
        """Alias for reconstruct_state with metadata wrapper."""
        state = self.reconstruct_state(entity_id, as_of)
        return {
            "snapshot_type": "point_in_time",
            "as_of": as_of.isoformat(),
            "entity_id": entity_id,
            "state": state,
        }

    def get_event_timeline(self, entity_id: str) -> list[dict]:
        """Return [{timestamp, action, actor_id, severity}] for display."""
        events = self._events.list_by_entity(entity_id, limit=10000)
        return [
            {
                "timestamp": e.timestamp.isoformat(),
                "action": e.action.value,
                "actor_id": e.actor_id,
                "severity": e.severity.value,
            }
            for e in sorted(events, key=lambda e: e.timestamp)
        ]
