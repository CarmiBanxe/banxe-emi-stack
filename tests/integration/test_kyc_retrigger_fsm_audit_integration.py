"""Integration tests for ADR-028 Step 5 — FSM call-site emits audit event.

These exercise services.customer_lifecycle.fsm.KYCLifecycleEngine
.notify_attribute_change against an in-memory event bus + a capturing
audit emitter (injected via constructor) and verify that the KYC
re-trigger path produces both:
  1) the existing DomainEvent on the bus (unchanged from Step 2)
  2) a new KYC_REVERIFICATION_TRIGGERED audit record (Step 5 hook)

No real audit subsystem, no real EventBus persistence beyond the
in-memory fake.
"""

from __future__ import annotations

from typing import Any

from services.customer_lifecycle.fsm import KYCLifecycleEngine
from services.events.event_bus import BanxeEventType, InMemoryEventBus


class _FakeAuditEmitter:
    """Capturing audit emitter — mirrors KycRetriggerAuditEmitter.emit shape."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def emit(
        self,
        customer_id: str,
        trigger_type: str,
        trigger_payload: dict,
        requested_by: str | None = None,
    ) -> None:
        self.calls.append(
            {
                "customer_id": customer_id,
                "trigger_type": trigger_type,
                "trigger_payload": dict(trigger_payload),
                "requested_by": requested_by,
            }
        )


def _engine_with_audit():
    bus = InMemoryEventBus()
    audit = _FakeAuditEmitter()
    engine = KYCLifecycleEngine(event_bus=bus, audit_emitter=audit)
    return engine, bus, audit


def test_fsm_role_change_publishes_event_and_emits_audit() -> None:
    engine, bus, audit = _engine_with_audit()
    engine.notify_attribute_change(
        customer_id="cust-role-1",
        event_type=BanxeEventType.ROLE_CHANGED,
        triggered_by="admin",
        previous_value="DIRECTOR",
        new_value="SHAREHOLDER",
    )
    # Existing behavior: DomainEvent on bus, ROLE_CHANGED-typed
    role_events = bus.events_of_type(BanxeEventType.ROLE_CHANGED)
    assert len(role_events) == 1
    # New behavior: audit emitter saw exactly one call
    assert len(audit.calls) == 1
    call = audit.calls[0]
    assert call["customer_id"] == "cust-role-1"
    assert call["trigger_type"] == "role_changed"
    assert call["requested_by"] == "admin"
    assert call["trigger_payload"]["previous_value"] == "DIRECTOR"
    assert call["trigger_payload"]["new_value"] == "SHAREHOLDER"
    # criticality + gap_ref come from build_kyc_retrigger_event
    assert call["trigger_payload"]["criticality"] == "HIGH"
    assert call["trigger_payload"]["gap_ref"] == "G-KYC-01"


def test_fsm_beneficial_owner_change_publishes_event_and_emits_audit() -> None:
    engine, bus, audit = _engine_with_audit()
    engine.notify_attribute_change(
        customer_id="cust-bo-1",
        event_type=BanxeEventType.BENEFICIAL_OWNER_CHANGED,
        triggered_by="compliance",
        previous_value="OWNER_A",
        new_value="OWNER_B",
    )
    assert len(bus.events_of_type(BanxeEventType.BENEFICIAL_OWNER_CHANGED)) == 1
    assert len(audit.calls) == 1
    assert audit.calls[0]["trigger_type"] == "beneficial_owner_changed"


def test_fsm_jurisdiction_change_publishes_event_and_emits_audit() -> None:
    engine, bus, audit = _engine_with_audit()
    engine.notify_attribute_change(
        customer_id="cust-jur-1",
        event_type=BanxeEventType.JURISDICTION_CHANGED,
        triggered_by="onboarding",
        previous_value="GB",
        new_value="DE",
    )
    assert len(bus.events_of_type(BanxeEventType.JURISDICTION_CHANGED)) == 1
    assert len(audit.calls) == 1
    assert audit.calls[0]["trigger_type"] == "jurisdiction_changed"


def test_fsm_audit_emitter_failure_does_not_block_event_publish() -> None:
    """A broken audit emitter MUST NOT prevent the DomainEvent from being
    published. Step 5 FSM hook wraps audit emission in
    contextlib.suppress(Exception)."""

    class _BrokenEmitter:
        def emit(self, **_kw: Any) -> None:
            raise RuntimeError("audit sink offline")

    bus = InMemoryEventBus()
    engine = KYCLifecycleEngine(event_bus=bus, audit_emitter=_BrokenEmitter())
    engine.notify_attribute_change(
        customer_id="cust-broken-audit",
        event_type=BanxeEventType.ROLE_CHANGED,
        triggered_by="admin",
        previous_value="X",
        new_value="Y",
    )
    # Event still on bus despite broken audit emitter
    assert len(bus.events_of_type(BanxeEventType.ROLE_CHANGED)) == 1


def test_fsm_audit_emission_does_not_break_existing_step2_contract() -> None:
    """Regression guard: KYCLifecycleEngine still records pending retrigger
    and the audit hook is purely additive."""
    engine, _bus, _audit = _engine_with_audit()
    retrigger = engine.notify_attribute_change(
        customer_id="cust-regression",
        event_type=BanxeEventType.ROLE_CHANGED,
        triggered_by="admin",
        previous_value="X",
        new_value="Y",
    )
    # Step 2 contract preserved
    assert retrigger.event_type == BanxeEventType.ROLE_CHANGED
    assert retrigger.customer_id == "cust-regression"
    assert engine.get_pending_retrigger("cust-regression") is retrigger
