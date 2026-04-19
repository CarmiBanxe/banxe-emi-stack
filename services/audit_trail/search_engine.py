"""
services/audit_trail/search_engine.py
IL-AES-01 | Phase 40 | banxe-emi-stack

SearchEngine — filtered, paginated search over audit events.
Supports category, severity, entity, actor, time range, and full-text filters.
"""

from __future__ import annotations

from services.audit_trail.models import (
    AuditEvent,
    EventStorePort,
    InMemoryEventStorePort,
    SearchQuery,
)


class SearchEngine:
    """Search and filter audit events with pagination support."""

    def __init__(self, event_port: EventStorePort | None = None) -> None:
        self._events: EventStorePort = event_port or InMemoryEventStorePort()

    def _all_events(self) -> list[AuditEvent]:
        if hasattr(self._events, "list_all"):
            return self._events.list_all()  # type: ignore[attr-defined]
        return []

    def search(self, query: SearchQuery) -> dict:
        """Filter and paginate events; return results with total/page/pages."""
        events = self._all_events()

        if query.categories:
            events = [e for e in events if e.category in query.categories]
        if query.severity:
            events = [e for e in events if e.severity == query.severity]
        if query.entity_id:
            events = [e for e in events if e.entity_id == query.entity_id]
        if query.actor_id:
            events = [e for e in events if e.actor_id == query.actor_id]
        if query.from_ts:
            events = [e for e in events if e.timestamp >= query.from_ts]
        if query.to_ts:
            events = [e for e in events if e.timestamp <= query.to_ts]

        events = sorted(events, key=lambda e: e.timestamp, reverse=True)
        total = len(events)
        page_size = max(1, query.page_size)
        page = max(1, query.page)
        offset = (page - 1) * page_size
        pages = max(1, (total + page_size - 1) // page_size)
        paginated = events[offset : offset + page_size]

        return {
            "results": paginated,
            "total": total,
            "page": page,
            "pages": pages,
        }

    def search_by_actor(self, actor_id: str, limit: int = 50) -> list[AuditEvent]:
        """Return most recent events by actor."""
        events = self._all_events()
        matches = [e for e in events if e.actor_id == actor_id]
        return sorted(matches, key=lambda e: e.timestamp, reverse=True)[:limit]

    def search_by_entity(self, entity_id: str, limit: int = 50) -> list[AuditEvent]:
        """Return most recent events for entity."""
        return self._events.list_by_entity(entity_id, limit)

    def full_text_search(self, text: str, limit: int = 20) -> list[AuditEvent]:
        """Search details dict values for text (case-insensitive)."""
        text_lower = text.lower()
        results: list[AuditEvent] = []
        for event in self._all_events():
            for val in event.details.values():
                if text_lower in str(val).lower():
                    results.append(event)
                    break
        return sorted(results, key=lambda e: e.timestamp, reverse=True)[:limit]

    def get_severity_summary(self) -> dict[str, int]:
        """Return {severity_name: count} across all events."""
        summary: dict[str, int] = {}
        for event in self._all_events():
            key = event.severity.value
            summary[key] = summary.get(key, 0) + 1
        return summary
