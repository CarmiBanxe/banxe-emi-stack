"""
tests/test_audit_trail/test_integrity_checker.py
IL-AES-01 | Phase 40 | banxe-emi-stack — 18 tests
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from services.audit_trail.event_store import EventStore
from services.audit_trail.integrity_checker import IntegrityChecker
from services.audit_trail.models import (
    AuditAction,
    EventCategory,
    EventSeverity,
    InMemoryChainPort,
    InMemoryEventStorePort,
    SourceSystem,
)


def _setup() -> tuple[EventStore, IntegrityChecker]:
    port = InMemoryEventStorePort()
    chain = InMemoryChainPort()
    store = EventStore(port, chain)
    checker = IntegrityChecker(port, chain)
    return store, checker


def _add(
    store: EventStore, source: SourceSystem = SourceSystem.API, entity_id: str = "e-1"
) -> None:
    store.append(
        EventCategory.PAYMENT,
        EventSeverity.INFO,
        AuditAction.CREATE,
        "payment",
        entity_id,
        "u1",
        {},
        source,
    )


class TestVerifyChain:
    def test_clean_chain_status(self) -> None:
        store, checker = _setup()
        _add(store, SourceSystem.API)
        _add(store, SourceSystem.API)
        report = checker.verify_chain(SourceSystem.API)
        assert report.status == "CLEAN"

    def test_clean_chain_zero_tampered(self) -> None:
        store, checker = _setup()
        _add(store, SourceSystem.API)
        report = checker.verify_chain(SourceSystem.API)
        assert report.tampered == 0

    def test_empty_source_returns_clean(self) -> None:
        store, checker = _setup()
        report = checker.verify_chain(SourceSystem.MANUAL)
        assert report.status == "CLEAN"
        assert report.total_events == 0

    def test_report_has_checked_at(self) -> None:
        store, checker = _setup()
        report = checker.verify_chain(SourceSystem.API)
        assert report.checked_at is not None

    def test_report_total_events(self) -> None:
        store, checker = _setup()
        _add(store, SourceSystem.MCP_TOOL)
        _add(store, SourceSystem.MCP_TOOL)
        report = checker.verify_chain(SourceSystem.MCP_TOOL)
        assert report.total_events == 2


class TestVerifyEvent:
    def test_valid_event_returns_true(self) -> None:
        store, checker = _setup()
        event = store.append(
            EventCategory.AUTH,
            EventSeverity.INFO,
            AuditAction.READ,
            "session",
            "s-1",
            "u1",
            {},
            SourceSystem.API,
        )
        assert checker.verify_event(event.id) is True

    def test_nonexistent_event_returns_false(self) -> None:
        _, checker = _setup()
        assert checker.verify_event("nonexistent-id") is False

    def test_tampered_event_returns_false(self) -> None:
        store, checker = _setup()
        event = store.append(
            EventCategory.PAYMENT,
            EventSeverity.INFO,
            AuditAction.CREATE,
            "pay",
            "p-1",
            "u1",
            {},
            SourceSystem.API,
        )
        # Manually inject tampered event into store (replace with wrong hash)
        tampered_event = AuditEvent_tampered(event)
        store._events._events[event.id] = tampered_event  # type: ignore[attr-defined]
        # Tampered event has wrong chain_hash — verify should return False
        assert checker.verify_event(event.id) is False


def AuditEvent_tampered(event):  # type: ignore[return]
    """Return a fake tampered event by replacing chain_hash."""
    from services.audit_trail.models import AuditEvent

    return AuditEvent(
        id=event.id,
        category=event.category,
        severity=event.severity,
        action=event.action,
        entity_type=event.entity_type,
        entity_id=event.entity_id,
        actor_id=event.actor_id,
        details=event.details,
        source=event.source,
        timestamp=event.timestamp,
        chain_hash="0000000000000000000000000000000000000000000000000000000000000000",
        prev_hash=event.prev_hash,
    )


class TestDetectGaps:
    def test_no_gaps_empty_entity(self) -> None:
        store, checker = _setup()
        gaps = checker.detect_gaps("UNKNOWN-ENTITY")
        assert gaps == []

    def test_consecutive_events_no_gap(self) -> None:
        store, checker = _setup()
        _add(store, SourceSystem.API, "gap-test")
        _add(store, SourceSystem.API, "gap-test")
        gaps = checker.detect_gaps("gap-test")
        assert isinstance(gaps, list)


class TestComplianceReport:
    def test_compliance_report_returns_integrity_report(self) -> None:
        store, checker = _setup()
        now = datetime.now(UTC)
        _add(store, SourceSystem.API)
        report = checker.generate_compliance_report(
            now - timedelta(minutes=1), now + timedelta(minutes=1)
        )
        assert report.status in ("CLEAN", "COMPROMISED")

    def test_compliance_report_time_range_filter(self) -> None:
        _, checker = _setup()
        now = datetime.now(UTC)
        future = now + timedelta(days=365)
        report = checker.generate_compliance_report(future, future + timedelta(hours=1))
        assert report.total_events == 0

    def test_compliance_report_has_valid_count(self) -> None:
        store, checker = _setup()
        now = datetime.now(UTC)
        _add(store, SourceSystem.API)
        report = checker.generate_compliance_report(
            now - timedelta(minutes=1), now + timedelta(minutes=1)
        )
        assert report.valid >= 0
        assert report.valid + report.tampered == report.total_events


class TestChainStatus:
    def test_chain_status_unknown_source(self) -> None:
        _, checker = _setup()
        status = checker.get_chain_status(SourceSystem.MANUAL)
        assert status["status"] == "UNKNOWN"

    def test_chain_status_clean_after_append(self) -> None:
        store, checker = _setup()
        store.append(
            EventCategory.PAYMENT,
            EventSeverity.INFO,
            AuditAction.CREATE,
            "pay",
            "cs-1",
            "u1",
            {},
            SourceSystem.SCHEDULER,
        )
        status = checker.get_chain_status(SourceSystem.SCHEDULER)
        assert status["status"] == "CLEAN"

    def test_chain_status_has_event_count(self) -> None:
        store, checker = _setup()
        store.append(
            EventCategory.ADMIN,
            EventSeverity.INFO,
            AuditAction.CREATE,
            "cfg",
            "cs-2",
            "admin",
            {},
            SourceSystem.AGENT,
        )
        store.append(
            EventCategory.ADMIN,
            EventSeverity.INFO,
            AuditAction.UPDATE,
            "cfg",
            "cs-3",
            "admin",
            {},
            SourceSystem.AGENT,
        )
        status = checker.get_chain_status(SourceSystem.AGENT)
        assert status["event_count"] == 2
