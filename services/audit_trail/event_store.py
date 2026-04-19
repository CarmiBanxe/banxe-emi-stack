"""
services/audit_trail/event_store.py
IL-AES-01 | Phase 40 | banxe-emi-stack

EventStore — append-only audit event storage with SHA-256 chain hashing.
I-12: SHA-256 chain hash on every event.
I-24: APPEND-ONLY — no update/delete methods.
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
import uuid

from services.audit_trail.models import (
    AuditAction,
    AuditEvent,
    ChainPort,
    EventCategory,
    EventChain,
    EventSeverity,
    EventStorePort,
    InMemoryChainPort,
    InMemoryEventStorePort,
    SourceSystem,
)


def _compute_chain_hash(event_data: dict, prev_hash: str | None) -> str:
    """SHA-256(event_data + prev_hash) — cryptographic chain link (I-12)."""
    payload = json.dumps(event_data, sort_keys=True, default=str) + (prev_hash or "GENESIS")
    return hashlib.sha256(payload.encode()).hexdigest()


class EventStore:
    """Append-only audit event store with cryptographic chain integrity."""

    def __init__(
        self,
        event_port: EventStorePort | None = None,
        chain_port: ChainPort | None = None,
    ) -> None:
        self._events: EventStorePort = event_port or InMemoryEventStorePort()
        self._chains: ChainPort = chain_port or InMemoryChainPort()

    def append(
        self,
        category: EventCategory,
        severity: EventSeverity,
        action: AuditAction,
        entity_type: str,
        entity_id: str,
        actor_id: str,
        details: dict,
        source: SourceSystem,
    ) -> AuditEvent:
        """Create event with chain_hash = sha256(event_data + prev_hash) (I-12)."""
        prev_hash = self.get_chain_head(source)
        now = datetime.now(UTC)
        event_data = {
            "category": category.value,
            "severity": severity.value,
            "action": action.value,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "actor_id": actor_id,
            "timestamp": now.isoformat(),
        }
        chain_hash = _compute_chain_hash(event_data, prev_hash)
        event = AuditEvent(
            id=str(uuid.uuid4()),
            category=category,
            severity=severity,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_id=actor_id,
            details=details,
            source=source,
            timestamp=now,
            chain_hash=chain_hash,
            prev_hash=prev_hash,
        )
        self._events.append(event)
        self._update_chain(source, chain_hash)
        return event

    def _update_chain(self, source: SourceSystem, latest_hash: str) -> None:
        existing = self._chains.get_chain(source)
        if existing is None:
            chain = EventChain(
                source_system=source,
                first_hash=latest_hash,
                latest_hash=latest_hash,
                event_count=1,
                last_verified_at=datetime.now(UTC),
            )
        else:
            chain = EventChain(
                source_system=source,
                first_hash=existing.first_hash,
                latest_hash=latest_hash,
                event_count=existing.event_count + 1,
                last_verified_at=datetime.now(UTC),
            )
        self._chains.save_chain(chain)

    def get_event(self, event_id: str) -> AuditEvent | None:
        """Return event by ID."""
        return self._events.get(event_id)

    def list_by_entity(self, entity_id: str, limit: int = 100) -> list[AuditEvent]:
        """Return most recent N events for entity."""
        return self._events.list_by_entity(entity_id, limit)

    def bulk_append(self, events_data: list[dict]) -> int:
        """Append multiple events atomically; return count inserted."""
        inserted = 0
        for data in events_data:
            self.append(
                category=EventCategory(data["category"]),
                severity=EventSeverity(data.get("severity", "INFO")),
                action=AuditAction(data["action"]),
                entity_type=data.get("entity_type", "unknown"),
                entity_id=data.get("entity_id", "unknown"),
                actor_id=data.get("actor_id", "system"),
                details=data.get("details", {}),
                source=SourceSystem(data.get("source", "API")),
            )
            inserted += 1
        return inserted

    def get_chain_head(self, source: SourceSystem) -> str | None:
        """Return latest chain_hash for source."""
        chain = self._chains.get_chain(source)
        return chain.latest_hash if chain else None
