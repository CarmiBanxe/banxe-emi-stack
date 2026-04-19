"""
services/audit_trail/integrity_checker.py
IL-AES-01 | Phase 40 | banxe-emi-stack

IntegrityChecker — cryptographic integrity verification for audit chains.
I-12: Recomputes SHA-256 chain hash to detect tampering.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import json

from services.audit_trail.models import (
    AuditEvent,
    ChainPort,
    EventStorePort,
    InMemoryChainPort,
    InMemoryEventStorePort,
    IntegrityReport,
    SourceSystem,
)


def _recompute_hash(event: AuditEvent) -> str:
    """Recompute chain hash from event fields."""
    event_data = {
        "category": event.category.value,
        "severity": event.severity.value,
        "action": event.action.value,
        "entity_type": event.entity_type,
        "entity_id": event.entity_id,
        "actor_id": event.actor_id,
        "timestamp": event.timestamp.isoformat(),
    }
    payload = json.dumps(event_data, sort_keys=True, default=str) + (event.prev_hash or "GENESIS")
    return hashlib.sha256(payload.encode()).hexdigest()


class IntegrityChecker:
    """Verifies cryptographic integrity of audit event chains."""

    def __init__(
        self,
        event_port: EventStorePort | None = None,
        chain_port: ChainPort | None = None,
    ) -> None:
        self._events: EventStorePort = event_port or InMemoryEventStorePort()
        self._chains: ChainPort = chain_port or InMemoryChainPort()

    def _all_events(self) -> list[AuditEvent]:
        if hasattr(self._events, "list_all"):
            return self._events.list_all()  # type: ignore[attr-defined]
        return []

    def verify_chain(self, source: SourceSystem) -> IntegrityReport:
        """Recompute chain_hash for each event; count tampered/gaps."""
        now = datetime.now(UTC)
        events = [e for e in self._all_events() if e.source == source]
        events = sorted(events, key=lambda e: e.timestamp)

        total = len(events)
        tampered = 0
        gaps = 0
        details: list[str] = []

        for i, event in enumerate(events):
            expected = _recompute_hash(event)
            if expected != event.chain_hash:
                tampered += 1
                details.append(f"Tampered event: {event.id}")

            if i > 0:
                prev = events[i - 1]
                delta = event.timestamp - prev.timestamp
                if delta > timedelta(hours=1):
                    gaps += 1
                    details.append(f"Gap detected between {prev.id} and {event.id}: {delta}")

        valid = total - tampered
        status = "CLEAN" if tampered == 0 else "COMPROMISED"
        return IntegrityReport(
            checked_at=now,
            total_events=total,
            valid=valid,
            tampered=tampered,
            gaps=gaps,
            status=status,
            details=details,
        )

    def verify_event(self, event_id: str) -> bool:
        """Recompute hash; compare to stored chain_hash."""
        event = self._events.get(event_id)
        if event is None:
            return False
        expected = _recompute_hash(event)
        return expected == event.chain_hash

    def detect_gaps(self, entity_id: str) -> list[dict]:
        """Check for timestamp gaps > 1 hour in event sequence."""
        events = sorted(
            self._events.list_by_entity(entity_id, limit=10000),
            key=lambda e: e.timestamp,
        )
        gaps: list[dict] = []
        for i in range(1, len(events)):
            prev = events[i - 1]
            curr = events[i]
            delta = curr.timestamp - prev.timestamp
            if delta > timedelta(hours=1):
                gaps.append(
                    {
                        "prev_event_id": prev.id,
                        "next_event_id": curr.id,
                        "gap_seconds": delta.total_seconds(),
                        "prev_ts": prev.timestamp.isoformat(),
                        "next_ts": curr.timestamp.isoformat(),
                    }
                )
        return gaps

    def generate_compliance_report(
        self,
        from_ts: datetime,
        to_ts: datetime,
    ) -> IntegrityReport:
        """Full integrity check over time range."""
        now = datetime.now(UTC)
        events = [e for e in self._all_events() if from_ts <= e.timestamp <= to_ts]
        total = len(events)
        tampered = 0
        gaps = 0
        details: list[str] = []

        for event in events:
            expected = _recompute_hash(event)
            if expected != event.chain_hash:
                tampered += 1
                details.append(f"Tampered event: {event.id}")

        valid = total - tampered
        status = "CLEAN" if tampered == 0 else "COMPROMISED"
        return IntegrityReport(
            checked_at=now,
            total_events=total,
            valid=valid,
            tampered=tampered,
            gaps=gaps,
            status=status,
            details=details,
        )

    def get_chain_status(self, source: SourceSystem) -> dict:
        """Return {source, event_count, status}."""
        chain = self._chains.get_chain(source)
        events = [e for e in self._all_events() if e.source == source]
        if not events:
            return {
                "source": source.value,
                "event_count": 0,
                "status": "UNKNOWN",
            }
        tampered = sum(1 for e in events if _recompute_hash(e) != e.chain_hash)
        return {
            "source": source.value,
            "event_count": len(events),
            "status": "CLEAN" if tampered == 0 else "COMPROMISED",
            "chain_head": chain.latest_hash if chain else None,
        }
