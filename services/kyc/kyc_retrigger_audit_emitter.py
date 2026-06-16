"""
kyc_retrigger_audit_emitter.py — KYC_REVERIFICATION_TRIGGERED audit emitter
(ADR-028 Step 4).

Bridges the KYC re-trigger path to the ADR-027 BufferedAuditPort ring buffer
and provides a thin wrapper (publish_kyc_retrigger_with_audit) that combines
event publication with audit emission under a contextlib.suppress guard so
audit-sink failure cannot break event delivery.

Event shape (per ADR-028 §Implementation-Plan item 3 + audit_trail.AuditEvent):
  event_type:  "KYC_REVERIFICATION_TRIGGERED"
  entity_id:   customer_id (plain — operational reference for ClickHouse
               partition + cross-event correlation)
  actor:       requested_by (or "LifecycleFSM" when None)
  severity:    AuditEvent vocabulary INFO | WARNING | MAJOR | CRITICAL,
               mapped from trigger_type via TRIGGER_SEVERITY
  payload:     {customer_id (sha256[:16] hashed for exfiltration safety),
                trigger_type, trigger_payload, requested_by}
  occurred_at: datetime.fromtimestamp(injected_clock(), tz=UTC)

ADR-028 §matrix vs repo BanxeEventType deviation note:
The Step 4 prompt requires 5 canonical trigger types (role_changed,
beneficial_owner_changed, sanctions_match, jurisdiction_changed,
periodic_review_due). The repo's BanxeEventType (services/events/event_bus.py)
currently has only 3 (ROLE_CHANGED, BENEFICIAL_OWNER_CHANGED,
JURISDICTION_CHANGED). The Port + emitter accept all 5 as strings; the
wrapper publish_kyc_retrigger_with_audit consumes KycReTriggerEvent
(BanxeEventType-shaped) and maps only the 3 representable values. Sanctions
and periodic-review trigger paths arrive via different upstream channels
not yet wired (deferred to subsequent steps / out of Step 4 scope).

Pure delegator inside the emitter (no try/except); defence-in-depth only in
the wrapper.
"""

from __future__ import annotations

from collections.abc import Callable
import contextlib
from datetime import UTC, datetime
import hashlib
import time
from typing import TYPE_CHECKING, Any

from src.safeguarding.audit_trail import AuditEvent

if TYPE_CHECKING:
    from src.safeguarding.buffered_audit_port import BufferedAuditPort


EVENT_KYC_REVERIFICATION_TRIGGERED = "KYC_REVERIFICATION_TRIGGERED"
_DEFAULT_ACTOR = "LifecycleFSM"

# Per Step 4 prompt — explicit severity per trigger type, in AuditEvent
# vocabulary (INFO / WARNING / MAJOR / CRITICAL).
TRIGGER_SEVERITY: dict[str, str] = {
    "sanctions_match": "CRITICAL",
    "role_changed": "CRITICAL",
    "beneficial_owner_changed": "MAJOR",
    "jurisdiction_changed": "MAJOR",
    "periodic_review_due": "WARNING",
}

# BanxeEventType.value → Port trigger_type string (used by the wrapper).
# Only the 3 currently-defined ADR-028 BanxeEventType values are mapped.
_BANXE_EVENT_TO_TRIGGER_TYPE: dict[str, str] = {
    "kyc.role_changed": "role_changed",
    "kyc.beneficial_owner_changed": "beneficial_owner_changed",
    "kyc.jurisdiction_changed": "jurisdiction_changed",
}


class KycRetriggerAuditEmitter:
    """Build and forward KYC_REVERIFICATION_TRIGGERED events to BufferedAuditPort."""

    def __init__(
        self,
        audit_port: BufferedAuditPort,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._audit = audit_port
        self._clock = clock

    def emit(
        self,
        customer_id: str,
        trigger_type: str,
        trigger_payload: dict,
        requested_by: str | None = None,
    ) -> None:
        if trigger_type not in TRIGGER_SEVERITY:
            raise ValueError(
                f"unknown trigger_type {trigger_type!r}; supported: {sorted(TRIGGER_SEVERITY)!r}"
            )
        severity = TRIGGER_SEVERITY[trigger_type]
        actor = requested_by or _DEFAULT_ACTOR
        event = AuditEvent(
            event_type=EVENT_KYC_REVERIFICATION_TRIGGERED,
            entity_id=customer_id,
            actor=actor,
            payload={
                "customer_id": hashlib.sha256(customer_id.encode("utf-8")).hexdigest()[:16],
                "trigger_type": trigger_type,
                "trigger_payload": dict(trigger_payload),
                "requested_by": requested_by,
            },
            severity=severity,
            occurred_at=datetime.fromtimestamp(self._clock(), tz=UTC),
        )
        self._audit.record(event)


def publish_kyc_retrigger_with_audit(
    event_bus: Any,
    audit_emitter: KycRetriggerAuditEmitter,
    event: Any,
) -> None:
    """Publish a KycReTriggerEvent then best-effort emit a matching audit record.

    Order: publish first, audit second. Event publication is the load-bearing
    operation; audit emission is best-effort and wrapped in
    contextlib.suppress(Exception) so a broken audit sink cannot break event
    delivery (defence-in-depth complementing ADR-027's own swallow).

    Events whose BanxeEventType has no entry in _BANXE_EVENT_TO_TRIGGER_TYPE
    (i.e. not one of the 3 currently-defined ADR-028 KYC re-trigger events)
    are published but no audit event is emitted from this wrapper.
    """
    event_bus.publish(event)
    trigger_type = _BANXE_EVENT_TO_TRIGGER_TYPE.get(event.event_type.value)
    if trigger_type is None:
        return
    with contextlib.suppress(Exception):
        audit_emitter.emit(
            customer_id=event.customer_id,
            trigger_type=trigger_type,
            trigger_payload={
                "previous_value": event.previous_value,
                "new_value": event.new_value,
                "criticality": event.criticality,
                "gap_ref": event.gap_ref,
            },
            requested_by=event.triggered_by,
        )
