"""End-to-end chain smoke for ADR-028 (Step 5).

Exercises the full FSM → DomainEvent bus → KYC_REVERIFICATION_TRIGGERED
audit chain for the 3 currently-supported BanxeEventType KYC re-trigger
events. No real audit subsystem; uses a capturing _FakeAuditEmitter that
mirrors KycRetriggerAuditEmitter.emit's shape.
"""

from __future__ import annotations

from typing import Any

import pytest

from services.customer_lifecycle.fsm import KYCLifecycleEngine
from services.events.event_bus import BanxeEventType, InMemoryEventBus
from services.kyc.kyc_retrigger_audit_emitter import (
    TRIGGER_SEVERITY,
)

pytestmark = pytest.mark.smoke


class _FakeAuditEmitter:
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


def test_smoke_full_role_changed_chain_event_to_audit() -> None:
    engine, bus, audit = _engine_with_audit()
    engine.notify_attribute_change(
        customer_id="cust-role-smoke",
        event_type=BanxeEventType.ROLE_CHANGED,
        triggered_by="admin",
        previous_value="DIRECTOR",
        new_value="SHAREHOLDER",
    )
    # Both legs of the chain fired
    assert len(bus.events_of_type(BanxeEventType.ROLE_CHANGED)) == 1
    assert len(audit.calls) == 1
    assert audit.calls[0]["trigger_type"] == "role_changed"


def test_smoke_full_beneficial_owner_changed_chain() -> None:
    engine, bus, audit = _engine_with_audit()
    engine.notify_attribute_change(
        customer_id="cust-bo-smoke",
        event_type=BanxeEventType.BENEFICIAL_OWNER_CHANGED,
        triggered_by="compliance",
        previous_value="OWNER_A",
        new_value="OWNER_B",
    )
    assert len(bus.events_of_type(BanxeEventType.BENEFICIAL_OWNER_CHANGED)) == 1
    assert len(audit.calls) == 1
    assert audit.calls[0]["trigger_type"] == "beneficial_owner_changed"


def test_smoke_full_jurisdiction_changed_chain() -> None:
    engine, bus, audit = _engine_with_audit()
    engine.notify_attribute_change(
        customer_id="cust-jur-smoke",
        event_type=BanxeEventType.JURISDICTION_CHANGED,
        triggered_by="onboarding",
        previous_value="GB",
        new_value="DE",
    )
    assert len(bus.events_of_type(BanxeEventType.JURISDICTION_CHANGED)) == 1
    assert len(audit.calls) == 1
    assert audit.calls[0]["trigger_type"] == "jurisdiction_changed"


def test_smoke_audit_severity_mapping_via_trigger_severity_table() -> None:
    """TRIGGER_SEVERITY (Step 4 module constant) correctly classifies the
    3 FSM-supported trigger types per ADR-028 §matrix."""
    assert TRIGGER_SEVERITY["role_changed"] == "CRITICAL"
    assert TRIGGER_SEVERITY["beneficial_owner_changed"] == "MAJOR"
    assert TRIGGER_SEVERITY["jurisdiction_changed"] == "MAJOR"


def test_smoke_audit_call_carries_criticality_and_gap_ref_from_event_payload() -> None:
    """The FSM-emitted audit call must surface criticality + gap_ref derived
    from build_kyc_retrigger_event so downstream consumers can dedupe /
    route by either field."""
    engine, _bus, audit = _engine_with_audit()
    engine.notify_attribute_change(
        customer_id="cust-payload-check",
        event_type=BanxeEventType.JURISDICTION_CHANGED,
        triggered_by="onboarding",
        previous_value="GB",
        new_value="DE",
    )
    payload = audit.calls[0]["trigger_payload"]
    # JURISDICTION_CHANGED → criticality=CRITICAL, gap_ref=G-KYC-02 per
    # _KYC_RETRIGGER_CRITICALITY / _KYC_RETRIGGER_GAP_REF in event_bus.
    assert payload["criticality"] == "CRITICAL"
    assert payload["gap_ref"] == "G-KYC-02"
    assert payload["previous_value"] == "GB"
    assert payload["new_value"] == "DE"


def test_smoke_broken_audit_emitter_does_not_break_fsm() -> None:
    """If the audit sink crashes, the FSM publish + retrigger record must
    still complete. Verified by the contextlib.suppress(Exception) guard
    around the audit call in fsm.notify_attribute_change."""

    class _Boom:
        def emit(self, **_kw: Any) -> None:
            raise RuntimeError("kaput")

    bus = InMemoryEventBus()
    engine = KYCLifecycleEngine(event_bus=bus, audit_emitter=_Boom())
    retrigger = engine.notify_attribute_change(
        customer_id="cust-suppress",
        event_type=BanxeEventType.ROLE_CHANGED,
        triggered_by="admin",
        previous_value="X",
        new_value="Y",
    )
    # FSM still produced the retrigger record AND published the event
    assert retrigger is not None
    assert retrigger.customer_id == "cust-suppress"
    assert len(bus.events_of_type(BanxeEventType.ROLE_CHANGED)) == 1
