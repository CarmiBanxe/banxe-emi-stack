"""Integration tests: ADR-028 Step 2 — KYC re-trigger events wired into lifecycle.

Gap refs: G-KYC-01 (role/UBO change) | G-KYC-02 (jurisdiction change)

Covers:
  T1 — ROLE_CHANGED sets pending re-verification flag (HIGH/G-KYC-01)
  T2 — BENEFICIAL_OWNER_CHANGED sets pending re-verification flag (HIGH/G-KYC-01)
  T3 — JURISDICTION_CHANGED sets CRITICAL flag and auto-suspends ACTIVE customer
  T4 — Unrelated DomainEvent does NOT trigger KYC re-verification
  T5 — notify_attribute_change publishes event to InMemoryEventBus
  T6 — JURISDICTION_CHANGED on non-ACTIVE customer sets flag but does NOT suspend
"""

from __future__ import annotations

from services.customer_lifecycle.fsm import (
    InMemoryKYCGuard,
    KYCLifecycleEngine,
)
from services.customer_lifecycle.lifecycle_models import CustomerState, LifecycleEvent
from services.customer_lifecycle.lifecycle_observer import InMemoryLifecycleObserver
from services.events.event_bus import BanxeEventType, DomainEvent, InMemoryEventBus
from services.kyc.kyc_port import KYCStatus


def _make_active_customer(engine: KYCLifecycleEngine, customer_id: str) -> None:
    """Helper: bring customer from PROSPECT → ACTIVE via normal lifecycle transitions."""
    engine.transition(customer_id, LifecycleEvent.SUBMIT_APPLICATION)
    engine.transition(customer_id, LifecycleEvent.COMPLETE_KYC)
    engine.transition(customer_id, LifecycleEvent.ACTIVATE)


# ---------------------------------------------------------------------------
# T1 — ROLE_CHANGED sets HIGH pending re-verification
# ---------------------------------------------------------------------------


def test_role_changed_triggers_kyc_reverification_flag() -> None:
    engine = KYCLifecycleEngine(kyc_guard=InMemoryKYCGuard(default=KYCStatus.APPROVED))

    engine.notify_attribute_change(
        customer_id="cust-role-01",
        event_type=BanxeEventType.ROLE_CHANGED,
        triggered_by="admin",
        previous_value="DIRECTOR",
        new_value="UBO",
    )

    pending = engine.get_pending_retrigger("cust-role-01")
    assert pending is not None
    assert pending.criticality == "HIGH"
    assert pending.gap_ref == "G-KYC-01"
    assert pending.event_type is BanxeEventType.ROLE_CHANGED
    assert pending.customer_id == "cust-role-01"


# ---------------------------------------------------------------------------
# T2 — BENEFICIAL_OWNER_CHANGED sets HIGH pending re-verification
# ---------------------------------------------------------------------------


def test_beneficial_owner_changed_triggers_kyc_reverification_flag() -> None:
    engine = KYCLifecycleEngine()

    engine.notify_attribute_change(
        customer_id="cust-ubo-01",
        event_type=BanxeEventType.BENEFICIAL_OWNER_CHANGED,
        triggered_by="kyc-agent",
        previous_value="Alice Smith",
        new_value="Bob Jones",
    )

    pending = engine.get_pending_retrigger("cust-ubo-01")
    assert pending is not None
    assert pending.criticality == "HIGH"
    assert pending.gap_ref == "G-KYC-01"


# ---------------------------------------------------------------------------
# T3 — JURISDICTION_CHANGED sets CRITICAL flag and auto-suspends ACTIVE customer
# ---------------------------------------------------------------------------


def test_jurisdiction_changed_sets_critical_flag_and_flows() -> None:
    kyc_guard = InMemoryKYCGuard(default=KYCStatus.APPROVED)
    observer = InMemoryLifecycleObserver()
    bus = InMemoryEventBus()
    engine = KYCLifecycleEngine(kyc_guard=kyc_guard, observer=observer, event_bus=bus)

    _make_active_customer(engine, "cust-jur-01")
    assert engine.get_state("cust-jur-01") == CustomerState.ACTIVE

    engine.notify_attribute_change(
        customer_id="cust-jur-01",
        event_type=BanxeEventType.JURISDICTION_CHANGED,
        triggered_by="ops-agent",
        previous_value="GB",
        new_value="IR",
    )

    pending = engine.get_pending_retrigger("cust-jur-01")
    assert pending is not None
    assert pending.criticality == "CRITICAL"
    assert pending.gap_ref == "G-KYC-02"

    # CRITICAL + ACTIVE → auto-suspended
    assert engine.get_state("cust-jur-01") == CustomerState.SUSPENDED

    # Event published to bus
    events = bus.events_of_type(BanxeEventType.JURISDICTION_CHANGED)
    assert len(events) == 1
    assert events[0].customer_id == "cust-jur-01"
    assert events[0].payload["criticality"] == "CRITICAL"


# ---------------------------------------------------------------------------
# T4 — Unrelated DomainEvent does NOT trigger KYC re-verification
# ---------------------------------------------------------------------------


def test_unrelated_event_does_not_trigger_kyc_reverification() -> None:
    bus = InMemoryEventBus()
    engine = KYCLifecycleEngine(event_bus=bus)

    bus.publish(
        DomainEvent.create(
            event_type=BanxeEventType.PAYMENT_COMPLETED,
            source_service="payment_service",
            payload={"amount": "100.00"},
            customer_id="cust-pay-01",
        )
    )

    assert engine.get_pending_retrigger("cust-pay-01") is None


# ---------------------------------------------------------------------------
# T5 — notify_attribute_change publishes event to InMemoryEventBus
# ---------------------------------------------------------------------------


def test_notify_attribute_change_publishes_to_event_bus() -> None:
    bus = InMemoryEventBus()
    engine = KYCLifecycleEngine(event_bus=bus)

    engine.notify_attribute_change(
        customer_id="cust-bus-01",
        event_type=BanxeEventType.ROLE_CHANGED,
        triggered_by="admin",
        previous_value="DIRECTOR",
        new_value="SHAREHOLDER",
    )

    events = bus.events_of_type(BanxeEventType.ROLE_CHANGED)
    assert len(events) == 1
    assert events[0].customer_id == "cust-bus-01"
    assert events[0].payload["gap_ref"] == "G-KYC-01"
    assert events[0].payload["triggered_by"] == "admin"


# ---------------------------------------------------------------------------
# T6 — JURISDICTION_CHANGED on non-ACTIVE customer sets flag but does NOT suspend
# ---------------------------------------------------------------------------


def test_jurisdiction_changed_on_non_active_does_not_suspend() -> None:
    engine = KYCLifecycleEngine()
    # Customer stays at PROSPECT (default)
    assert engine.get_state("cust-jur-02") == CustomerState.PROSPECT

    engine.notify_attribute_change(
        customer_id="cust-jur-02",
        event_type=BanxeEventType.JURISDICTION_CHANGED,
        triggered_by="system",
        previous_value="US",
        new_value="KP",
    )

    pending = engine.get_pending_retrigger("cust-jur-02")
    assert pending is not None
    assert pending.criticality == "CRITICAL"
    # No suspend — PROSPECT has no SUSPEND transition
    assert engine.get_state("cust-jur-02") == CustomerState.PROSPECT
