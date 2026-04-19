"""
services/audit_trail/models.py
IL-AES-01 | Phase 40 | banxe-emi-stack

Domain models, protocols, and in-memory stubs for Audit Trail & Event Sourcing.
Protocol DI: Port (Protocol) → InMemory stub (tests) → Real adapter (production)
I-12: SHA-256 chain hash on every audit event.
I-24: EventStore is APPEND-ONLY — no update/delete.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Protocol
import uuid

# ── Enums ────────────────────────────────────────────────────────────────────


class EventCategory(str, Enum):
    PAYMENT = "PAYMENT"
    COMPLIANCE = "COMPLIANCE"
    AUTH = "AUTH"
    ADMIN = "ADMIN"
    SYSTEM = "SYSTEM"
    AML = "AML"
    CUSTOMER = "CUSTOMER"


class EventSeverity(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class RetentionPolicy(str, Enum):
    AML_5YR = "AML_5YR"
    FINANCIAL_7YR = "FINANCIAL_7YR"
    OPERATIONAL_3YR = "OPERATIONAL_3YR"
    SYSTEM_1YR = "SYSTEM_1YR"


class SourceSystem(str, Enum):
    API = "API"
    MCP_TOOL = "MCP_TOOL"
    AGENT = "AGENT"
    SCHEDULER = "SCHEDULER"
    MIGRATION = "MIGRATION"
    MANUAL = "MANUAL"


class AuditAction(str, Enum):
    CREATE = "CREATE"
    READ = "READ"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    ESCALATE = "ESCALATE"
    EXPORT = "EXPORT"


# ── Dataclasses ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AuditEvent:
    id: str
    category: EventCategory
    severity: EventSeverity
    action: AuditAction
    entity_type: str
    entity_id: str
    actor_id: str
    details: dict
    source: SourceSystem
    timestamp: datetime
    chain_hash: str
    prev_hash: str | None = None


@dataclass(frozen=True)
class EventChain:
    source_system: SourceSystem
    first_hash: str
    latest_hash: str
    event_count: int
    last_verified_at: datetime


@dataclass(frozen=True)
class RetentionRule:
    policy: RetentionPolicy
    retention_days: int
    category: EventCategory
    purge_requires_hitl: bool


@dataclass(frozen=True)
class SearchQuery:
    page: int = 1
    page_size: int = 20
    categories: list[EventCategory] | None = None
    severity: EventSeverity | None = None
    entity_id: str | None = None
    actor_id: str | None = None
    from_ts: datetime | None = None
    to_ts: datetime | None = None


@dataclass(frozen=True)
class IntegrityReport:
    checked_at: datetime
    total_events: int
    valid: int
    tampered: int
    gaps: int
    status: str  # "CLEAN" | "COMPROMISED"
    details: list[str] = field(default_factory=list)


# ── Protocols ────────────────────────────────────────────────────────────────


class EventStorePort(Protocol):
    def append(self, event: AuditEvent) -> None: ...
    def get(self, id: str) -> AuditEvent | None: ...
    def list_by_entity(self, entity_id: str, limit: int) -> list[AuditEvent]: ...
    def bulk_append(self, events: list[AuditEvent]) -> int: ...


class ChainPort(Protocol):
    def get_chain(self, source: SourceSystem) -> EventChain | None: ...
    def save_chain(self, c: EventChain) -> None: ...


class RetentionPort(Protocol):
    def get_rule(self, policy: RetentionPolicy) -> RetentionRule: ...
    def list_rules(self) -> list[RetentionRule]: ...


class AuditPort(Protocol):
    def log(self, action: str, resource_id: str, details: dict, outcome: str) -> None: ...


# ── InMemory Stubs ────────────────────────────────────────────────────────────


class InMemoryEventStorePort:
    def __init__(self) -> None:
        self._events: dict[str, AuditEvent] = {}
        self._seed()

    def _seed(self) -> None:
        import hashlib
        import json

        now = datetime.now(UTC)

        def _make_hash(data: dict, prev: str | None) -> str:
            payload = json.dumps(data, sort_keys=True, default=str) + (prev or "GENESIS")
            return hashlib.sha256(payload.encode()).hexdigest()

        seed_data = [
            (
                EventCategory.PAYMENT,
                EventSeverity.INFO,
                AuditAction.CREATE,
                "payment",
                "PAY-001",
                "USR-001",
                {"amount": "100.00"},
            ),
            (
                EventCategory.PAYMENT,
                EventSeverity.INFO,
                AuditAction.APPROVE,
                "payment",
                "PAY-002",
                "USR-002",
                {"amount": "500.00"},
            ),
            (
                EventCategory.AML,
                EventSeverity.WARNING,
                AuditAction.ESCALATE,
                "transaction",
                "TXN-001",
                "AGENT",
                {"reason": "threshold_exceeded"},
            ),
            (
                EventCategory.AUTH,
                EventSeverity.ERROR,
                AuditAction.REJECT,
                "session",
                "SES-001",
                "USR-003",
                {"reason": "invalid_token"},
            ),
            (
                EventCategory.ADMIN,
                EventSeverity.INFO,
                AuditAction.UPDATE,
                "config",
                "CFG-001",
                "ADMIN",
                {"field": "limit"},
            ),
        ]
        prev_hash: str | None = None
        for cat, sev, act, etype, eid, actor, details in seed_data:
            eid_str = str(uuid.uuid4())
            event_data = {
                "category": cat.value,
                "severity": sev.value,
                "action": act.value,
                "entity_type": etype,
                "entity_id": eid,
                "actor_id": actor,
                "timestamp": now.isoformat(),
            }
            chain_hash = _make_hash(event_data, prev_hash)
            event = AuditEvent(
                id=eid_str,
                category=cat,
                severity=sev,
                action=act,
                entity_type=etype,
                entity_id=eid,
                actor_id=actor,
                details=details,
                source=SourceSystem.MIGRATION,
                timestamp=now,
                chain_hash=chain_hash,
                prev_hash=prev_hash,
            )
            self._events[eid_str] = event
            prev_hash = chain_hash

    def append(self, event: AuditEvent) -> None:
        self._events[event.id] = event

    def get(self, id: str) -> AuditEvent | None:
        return self._events.get(id)

    def list_by_entity(self, entity_id: str, limit: int = 100) -> list[AuditEvent]:
        matches = [e for e in self._events.values() if e.entity_id == entity_id]
        return sorted(matches, key=lambda e: e.timestamp, reverse=True)[:limit]

    def bulk_append(self, events: list[AuditEvent]) -> int:
        for event in events:
            self._events[event.id] = event
        return len(events)

    def list_all(self) -> list[AuditEvent]:
        return list(self._events.values())


class InMemoryChainPort:
    def __init__(self) -> None:
        self._chains: dict[str, EventChain] = {}

    def get_chain(self, source: SourceSystem) -> EventChain | None:
        return self._chains.get(source.value)

    def save_chain(self, c: EventChain) -> None:
        self._chains[c.source_system.value] = c


class InMemoryRetentionPort:
    def __init__(self, rules: dict[RetentionPolicy, RetentionRule] | None = None) -> None:
        self._rules = rules or {}

    def get_rule(self, policy: RetentionPolicy) -> RetentionRule:
        if policy not in self._rules:
            raise KeyError(f"No rule for policy: {policy.value}")
        return self._rules[policy]

    def list_rules(self) -> list[RetentionRule]:
        return list(self._rules.values())


class InMemoryAuditMetaPort:
    def __init__(self) -> None:
        self._log: list[dict] = []

    def log(self, action: str, resource_id: str, details: dict, outcome: str) -> None:
        self._log.append(
            {
                "action": action,
                "resource_id": resource_id,
                "details": details,
                "outcome": outcome,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

    def entries(self) -> list[dict]:
        return list(self._log)
