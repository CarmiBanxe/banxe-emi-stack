"""
services/audit_dashboard/audit_aggregator.py
IL-AGD-01 | Phase 16

Aggregates audit events from all services into a unified view.
Queries ClickHouse banxe.* audit tables and normalises into AuditEvent.
"""

from __future__ import annotations

from datetime import UTC, datetime
import uuid

from services.audit_dashboard.models import (
    AuditEvent,
    EventCategory,
    EventStorePort,
    RiskLevel,
)


class AuditAggregator:
    """Unified aggregator for all audit events across Banxe services."""

    def __init__(self, store: EventStorePort) -> None:
        self._store = store

    async def ingest_event(
        self,
        category: EventCategory,
        event_type: str,
        entity_id: str,
        actor: str,
        details: dict,
        risk_level: RiskLevel,
        source_service: str,
    ) -> AuditEvent:
        """Create an AuditEvent with a UUID id and UTC timestamp, persist it."""
        event = AuditEvent(
            id=str(uuid.uuid4()),
            category=category,
            event_type=event_type,
            entity_id=entity_id,
            actor=actor,
            details=details,
            risk_level=risk_level,
            created_at=datetime.now(UTC),
            source_service=source_service,
        )
        await self._store.ingest(event)
        return event

    async def query_events(
        self,
        category: EventCategory | None = None,
        entity_id: str | None = None,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
        risk_level: RiskLevel | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        """Delegate event query to the backing store."""
        return await self._store.query_events(
            category=category,
            entity_id=entity_id,
            from_dt=from_dt,
            to_dt=to_dt,
            risk_level=risk_level,
            limit=limit,
        )

    async def get_event_summary(self, from_dt: datetime, to_dt: datetime) -> dict:
        """
        Return a summary dict for events in the given time window.

        Keys: total, by_category, by_risk_level, high_risk_count
        """
        events = await self._store.query_events(from_dt=from_dt, to_dt=to_dt, limit=10_000)

        by_category: dict[str, int] = {}
        by_risk_level: dict[str, int] = {}
        high_risk_count = 0

        for event in events:
            cat_key = event.category.value
            by_category[cat_key] = by_category.get(cat_key, 0) + 1

            rl_key = event.risk_level.value
            by_risk_level[rl_key] = by_risk_level.get(rl_key, 0) + 1

            if event.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
                high_risk_count += 1

        return {
            "total": len(events),
            "by_category": by_category,
            "by_risk_level": by_risk_level,
            "high_risk_count": high_risk_count,
        }

    async def get_entity_timeline(self, entity_id: str, limit: int = 50) -> list[AuditEvent]:
        """Return events for an entity ordered by created_at descending."""
        events = await self._store.query_events(entity_id=entity_id, limit=10_000)
        sorted_events = sorted(events, key=lambda e: e.created_at, reverse=True)
        return sorted_events[:limit]


__all__ = ["AuditAggregator"]
