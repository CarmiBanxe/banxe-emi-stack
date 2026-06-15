"""Integration tests for publish_kyc_retrigger_with_audit (ADR-028 Step 4).

Verify the wrapper publishes events to the (in-memory) bus FIRST and then
best-effort emits an audit record. Audit emitter failures must NOT block
event delivery — contextlib.suppress guard in the wrapper.
"""

from __future__ import annotations

from typing import Any

from services.events.event_bus import (
    BanxeEventType,
    KycReTriggerEvent,
    build_kyc_retrigger_event,
)
from services.kyc.kyc_retrigger_audit_emitter import (
    EVENT_KYC_REVERIFICATION_TRIGGERED,
    KycRetriggerAuditEmitter,
    publish_kyc_retrigger_with_audit,
)


class _FakeAuditPort:
    def __init__(self) -> None:
        self.records: list[Any] = []

    def record(self, entry: Any) -> None:
        self.records.append(entry)


class _FakeBus:
    """Minimal EventBusPort.publish(event) double — KycReTriggerEvent is
    a plain dataclass without DomainEvent.event_id, so the real
    InMemoryEventBus (which logs event.event_id) can't accept it directly.
    This fake records every published event for assertion.
    """

    def __init__(self) -> None:
        self.published: list[Any] = []

    def publish(self, event: Any) -> None:
        self.published.append(event)


def _build_event(
    event_type: BanxeEventType = BanxeEventType.ROLE_CHANGED,
    customer_id: str = "cust-banxe-001",
) -> KycReTriggerEvent:
    return build_kyc_retrigger_event(
        event_type=event_type,
        customer_id=customer_id,
        triggered_by="lifecycle-observer",
        previous_value="BENEFICIARY",
        new_value="DIRECTOR",
    )


def test_wrapper_publishes_event_then_emits_audit() -> None:
    bus = _FakeBus()
    audit_port = _FakeAuditPort()
    emitter = KycRetriggerAuditEmitter(audit_port=audit_port, clock=lambda: 1714000000.0)

    event = _build_event()
    publish_kyc_retrigger_with_audit(bus, emitter, event)

    # Event published exactly once
    assert len(bus.published) == 1
    assert bus.published[0] is event
    # Audit record emitted exactly once with correct shape
    assert len(audit_port.records) == 1
    rec = audit_port.records[0]
    assert rec.event_type == EVENT_KYC_REVERIFICATION_TRIGGERED
    assert rec.entity_id == "cust-banxe-001"
    assert rec.severity == "CRITICAL"  # role_changed → CRITICAL
    assert rec.payload["trigger_type"] == "role_changed"
    assert rec.payload["trigger_payload"]["previous_value"] == "BENEFICIARY"
    assert rec.payload["trigger_payload"]["new_value"] == "DIRECTOR"
    assert rec.payload["trigger_payload"]["criticality"] == "HIGH"
    assert rec.payload["trigger_payload"]["gap_ref"] == "G-KYC-01"
    assert rec.payload["requested_by"] == "lifecycle-observer"
    assert rec.actor == "lifecycle-observer"


def test_wrapper_audit_emission_failure_does_not_break_event_publish() -> None:
    """A broken audit emitter MUST NOT block event delivery."""
    bus = _FakeBus()

    class _BrokenEmitter:
        def emit(self, **_kw: Any) -> None:
            raise RuntimeError("audit sink offline")

    event = _build_event()
    publish_kyc_retrigger_with_audit(bus, _BrokenEmitter(), event)

    # Event STILL published despite emitter explosion
    assert len(bus.published) == 1
    assert bus.published[0] is event


def test_wrapper_extracts_fields_from_kyc_retrigger_event_dataclass_correctly() -> None:
    """All three repo-supported BanxeEventType values map to the right
    Port trigger_type strings + severity."""
    bus = _FakeBus()
    audit_port = _FakeAuditPort()
    emitter = KycRetriggerAuditEmitter(audit_port=audit_port, clock=lambda: 1714000000.0)

    cases = [
        (BanxeEventType.ROLE_CHANGED, "role_changed", "CRITICAL"),
        (BanxeEventType.BENEFICIAL_OWNER_CHANGED, "beneficial_owner_changed", "MAJOR"),
        (BanxeEventType.JURISDICTION_CHANGED, "jurisdiction_changed", "MAJOR"),
    ]
    for event_type, expected_trigger, expected_severity in cases:
        event = _build_event(event_type=event_type, customer_id=f"cust-{event_type.name}")
        publish_kyc_retrigger_with_audit(bus, emitter, event)

    assert len(bus.published) == 3
    assert len(audit_port.records) == 3
    by_entity = {r.entity_id: r for r in audit_port.records}
    for event_type, expected_trigger, expected_severity in cases:
        rec = by_entity[f"cust-{event_type.name}"]
        assert rec.payload["trigger_type"] == expected_trigger
        assert rec.severity == expected_severity
