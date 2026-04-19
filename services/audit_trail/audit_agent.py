"""
services/audit_trail/audit_agent.py
IL-AES-01 | Phase 40 | banxe-emi-stack

AuditAgent — orchestrates audit trail operations.
L1: auto log/search/replay/integrity.
L4: purge is always HITL (I-27 — irreversible).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from services.audit_trail.event_replayer import EventReplayer
from services.audit_trail.event_store import EventStore
from services.audit_trail.integrity_checker import IntegrityChecker
from services.audit_trail.models import (
    AuditAction,
    EventCategory,
    EventSeverity,
    SearchQuery,
    SourceSystem,
)
from services.audit_trail.retention_enforcer import RetentionEnforcer
from services.audit_trail.search_engine import SearchEngine


@dataclass
class HITLProposal:
    action: str
    resource_id: str
    requires_approval_from: str
    reason: str
    autonomy_level: str = "L4"


class AuditAgent:
    """Facade agent for audit trail operations."""

    def __init__(self) -> None:
        self._store = EventStore()
        self._replayer = EventReplayer(self._store._events)
        self._searcher = SearchEngine(self._store._events)
        self._integrity = IntegrityChecker(self._store._events, self._store._chains)
        self._retention = RetentionEnforcer(self._store._events)

    def process_log_request(
        self,
        category: EventCategory,
        action: AuditAction,
        entity_id: str,
        details: dict,
    ) -> dict:
        """Auto-log event (L1); return event summary."""
        event = self._store.append(
            category=category,
            severity=EventSeverity.INFO,
            action=action,
            entity_type="generic",
            entity_id=entity_id,
            actor_id="agent",
            details=details,
            source=SourceSystem.AGENT,
        )
        return {
            "event_id": event.id,
            "category": event.category.value,
            "action": event.action.value,
            "entity_id": entity_id,
            "timestamp": event.timestamp.isoformat(),
            "chain_hash": event.chain_hash,
            "autonomy_level": "L1",
        }

    def process_search_request(self, query: SearchQuery) -> dict:
        """Auto-search (L1); return results."""
        result = self._searcher.search(query)
        events = result["results"]
        return {
            "total": result["total"],
            "page": result["page"],
            "pages": result["pages"],
            "events": [
                {
                    "id": e.id,
                    "category": e.category.value,
                    "action": e.action.value,
                    "entity_id": e.entity_id,
                    "timestamp": e.timestamp.isoformat(),
                }
                for e in events
            ],
            "autonomy_level": "L1",
        }

    def process_replay_request(
        self,
        entity_id: str,
        from_ts: datetime,
        to_ts: datetime,
    ) -> dict:
        """Auto-replay (L1); return event list."""
        events = self._replayer.replay_entity(entity_id, from_ts, to_ts)
        return {
            "entity_id": entity_id,
            "from_ts": from_ts.isoformat(),
            "to_ts": to_ts.isoformat(),
            "event_count": len(events),
            "events": [
                {
                    "id": e.id,
                    "action": e.action.value,
                    "timestamp": e.timestamp.isoformat(),
                }
                for e in events
            ],
            "autonomy_level": "L1",
        }

    def process_purge_request(
        self,
        category: EventCategory,
        older_than_days: int,
    ) -> HITLProposal:
        """Purge is ALWAYS HITL — irreversible (I-27)."""
        proposal = self._retention.schedule_purge(category, older_than_days)
        return HITLProposal(
            action=proposal.action,
            resource_id=proposal.resource_id,
            requires_approval_from=proposal.requires_approval_from,
            reason=proposal.reason,
            autonomy_level="L4",
        )

    def process_integrity_check(self, source: SourceSystem) -> dict:
        """Auto-check integrity (L1); return report."""
        report = self._integrity.verify_chain(source)
        return {
            "source": source.value,
            "checked_at": report.checked_at.isoformat(),
            "total_events": report.total_events,
            "valid": report.valid,
            "tampered": report.tampered,
            "gaps": report.gaps,
            "status": report.status,
            "autonomy_level": "L1",
        }

    def get_agent_status(self) -> dict:
        """Return agent operational status."""
        return {
            "agent": "AuditAgent",
            "status": "operational",
            "autonomy_level": "L1/L4",
            "hitl_gates": ["purge_audit_records"],
            "il": "IL-AES-01",
        }
