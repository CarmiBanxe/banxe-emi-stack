"""
services/customer_lifecycle/fsm.py
KYC/EDD-gated Customer Lifecycle FSM (IL-KYC-01 + IL-OBS-01).

Wraps LifecycleEngine with guards:
  - KYC_PENDING → ACTIVE  : requires KYC APPROVED signal (KYCGuardPort)
  - ACTIVE → SUSPENDED    : triggered by EDD breach >£10k individual (I-04)
  - SUSPENDED → ACTIVE    : requires MLRO HITL L4 approval (I-27)
  - ACTIVE/DORMANT → CLOSED: requires FATCA/CRS reporting complete

Observability (IL-OBS-01): LifecycleObserverPort injected for transition/guard/EDD events.
Invariants: I-01 (Decimal), I-02 (jurisdictions), I-04 (EDD), I-24 (append-only), I-27 (HITL L4).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from services.aml.aml_thresholds import get_thresholds
from services.customer_lifecycle.lifecycle_engine import (
    InMemoryLifecycleStore,
    LifecycleEngine,
)
from services.customer_lifecycle.lifecycle_models import (
    CustomerState,
    LifecycleEvent,
    TransitionResult,
)
from services.customer_lifecycle.lifecycle_observer import (
    EddBreachObservedEvent,
    GuardFailureEvent,
    LifecycleObserverPort,
    TransitionObservedEvent,
    _decimal_str,
)
from services.events.event_bus import (
    BanxeEventType,
    DomainEvent,
    EventBusPort,
    KycReTriggerEvent,
    build_kyc_retrigger_event,
)
from services.kyc.kyc_port import KYCStatus

# ADR-028 Step 5: BanxeEventType.value → Port trigger_type string mapping
# (mirrored from services.kyc.kyc_retrigger_audit_emitter; kept here as a
# module-local constant to avoid pulling the audit-emitter module into
# fsm.py's import chain when no audit is wired).
_BANXE_EVENT_TO_TRIGGER_TYPE: dict[str, str] = {
    "kyc.role_changed": "role_changed",
    "kyc.beneficial_owner_changed": "beneficial_owner_changed",
    "kyc.jurisdiction_changed": "jurisdiction_changed",
}

# ── Narrow ports for lifecycle guards ─────────────────────────────────────────


class KYCGuardPort(Protocol):
    """Narrow lifecycle port: only KYC approval status is needed."""

    def get_status(self, customer_id: str) -> KYCStatus: ...


class FatcaCrsPort(Protocol):
    """Check whether FATCA/CRS reporting is complete for a customer."""

    def is_reporting_complete(self, customer_id: str) -> bool: ...


class HITLLifecyclePort(Protocol):
    """Check whether MLRO has granted lifecycle gate approval."""

    def has_mlro_approval(self, customer_id: str, gate: str) -> bool: ...


# ── In-memory stubs (for tests) ───────────────────────────────────────────────


class InMemoryKYCGuard:
    """Configurable KYC stub: set status per customer_id."""

    def __init__(self, default: KYCStatus = KYCStatus.PENDING) -> None:
        self._statuses: dict[str, KYCStatus] = {}
        self._default = default

    def set_status(self, customer_id: str, status: KYCStatus) -> None:
        self._statuses[customer_id] = status

    def get_status(self, customer_id: str) -> KYCStatus:
        return self._statuses.get(customer_id, self._default)


class InMemoryFatcaCrsGuard:
    """Configurable FATCA/CRS stub: incomplete customers can be registered."""

    def __init__(self, default_complete: bool = True) -> None:
        self._incomplete: set[str] = set()
        self._default_complete = default_complete

    def mark_incomplete(self, customer_id: str) -> None:
        self._incomplete.add(customer_id)

    def mark_complete(self, customer_id: str) -> None:
        self._incomplete.discard(customer_id)

    def is_reporting_complete(self, customer_id: str) -> bool:
        if customer_id in self._incomplete:
            return False
        return self._default_complete


class InMemoryHITLLifecyclePort:
    """Configurable HITL stub: approve/deny MLRO gates."""

    def __init__(self) -> None:
        self._approvals: set[tuple[str, str]] = set()

    def grant_approval(self, customer_id: str, gate: str) -> None:
        self._approvals.add((customer_id, gate))

    def revoke_approval(self, customer_id: str, gate: str) -> None:
        self._approvals.discard((customer_id, gate))

    def has_mlro_approval(self, customer_id: str, gate: str) -> bool:
        return (customer_id, gate) in self._approvals


# ── Guard errors ──────────────────────────────────────────────────────────────


class KYCNotApprovedError(ValueError):
    """Raised when KYC is not APPROVED and activation is attempted."""


class HITLRequiredError(ValueError):
    """Raised when MLRO HITL L4 approval is required but absent (I-27)."""


class FatcaCrsIncompleteError(ValueError):
    """Raised when FATCA/CRS reporting is outstanding and close is attempted."""


class EddBreachError(ValueError):
    """Raised (informational) when EDD restriction is triggered (I-04)."""


# ── KYC-gated lifecycle engine ────────────────────────────────────────────────

_HITL_GATE_RESTRICTED_TO_ACTIVE = "restricted_to_customer"


class KYCLifecycleEngine:
    """
    Customer Lifecycle FSM with KYC/EDD/HITL guards (IL-KYC-01).

    I-01: EDD threshold comparison uses Decimal — never float.
    I-02: blocked jurisdictions enforced on SUBMIT_APPLICATION (delegated to LifecycleEngine).
    I-04: EDD trigger for INDIVIDUAL ≥£10,000; COMPANY ≥£50,000.
    I-27: SUSPENDED→ACTIVE requires explicit MLRO approval; no auto-resolution.
    """

    def __init__(
        self,
        engine: LifecycleEngine | None = None,
        kyc_guard: KYCGuardPort | None = None,
        fatca_crs: FatcaCrsPort | None = None,
        hitl: HITLLifecyclePort | None = None,
        observer: LifecycleObserverPort | None = None,
        event_bus: EventBusPort | None = None,
        audit_emitter: object | None = None,
    ) -> None:
        self._engine = engine or LifecycleEngine(InMemoryLifecycleStore())
        self._kyc: KYCGuardPort = kyc_guard or InMemoryKYCGuard()
        self._fatca_crs: FatcaCrsPort = fatca_crs or InMemoryFatcaCrsGuard()
        self._hitl: HITLLifecyclePort = hitl or InMemoryHITLLifecyclePort()
        self._observer: LifecycleObserverPort | None = observer
        self._event_bus: EventBusPort | None = event_bus
        # ADR-028 Step 5: optional KYC re-trigger audit emitter. When None,
        # falls back to the lazy factory singleton inside notify_attribute_change.
        self._audit_emitter: object | None = audit_emitter
        self._pending_retriggers: dict[str, KycReTriggerEvent] = {}

    def transition(
        self,
        customer_id: str,
        event: LifecycleEvent,
        country: str = "GB",
    ) -> TransitionResult | None:
        """Execute lifecycle transition with KYC/EDD/HITL guards.

        Raises:
            KYCNotApprovedError: ACTIVATE from KYC_PENDING without APPROVED KYC.
            HITLRequiredError: ACTIVATE from SUSPENDED without MLRO approval (I-27).
            FatcaCrsIncompleteError: CLOSE with outstanding FATCA/CRS reporting.
            ValueError: blocked jurisdiction on SUBMIT_APPLICATION (I-02).
        """
        current = self._engine.get_state(customer_id)

        # Guard: KYC_PENDING → ACTIVE requires KYC APPROVED
        if event == LifecycleEvent.ACTIVATE and current == CustomerState.KYC_PENDING:
            status = self._kyc.get_status(customer_id)
            if status != KYCStatus.APPROVED:
                detail = (
                    f"Customer {customer_id!r} KYC status is {status.value!r}; "
                    "APPROVED required before activation."
                )
                if self._observer is not None:
                    self._observer.on_guard_failure(
                        GuardFailureEvent(
                            customer_id=customer_id,
                            guard_type="KYC_NOT_APPROVED",
                            detail=detail,
                        )
                    )
                raise KYCNotApprovedError(detail)

        # Guard: SUSPENDED → ACTIVE requires MLRO HITL L4 approval (I-27)
        if event == LifecycleEvent.ACTIVATE and current == CustomerState.SUSPENDED:
            if not self._hitl.has_mlro_approval(customer_id, _HITL_GATE_RESTRICTED_TO_ACTIVE):
                detail = (
                    f"Customer {customer_id!r} requires MLRO L4 approval "
                    f"(gate={_HITL_GATE_RESTRICTED_TO_ACTIVE!r}) before reactivation (I-27)."
                )
                if self._observer is not None:
                    self._observer.on_guard_failure(
                        GuardFailureEvent(
                            customer_id=customer_id,
                            guard_type="HITL_REQUIRED",
                            detail=detail,
                        )
                    )
                raise HITLRequiredError(detail)

        # Guard: CLOSE requires FATCA/CRS reporting complete
        if event == LifecycleEvent.CLOSE:
            if not self._fatca_crs.is_reporting_complete(customer_id):
                detail = (
                    f"Customer {customer_id!r} has outstanding FATCA/CRS reporting; "
                    "cannot close until reporting is complete."
                )
                if self._observer is not None:
                    self._observer.on_guard_failure(
                        GuardFailureEvent(
                            customer_id=customer_id,
                            guard_type="FATCA_CRS_INCOMPLETE",
                            detail=detail,
                        )
                    )
                raise FatcaCrsIncompleteError(detail)

        result = self._engine.transition(customer_id, event, country)
        if result is not None and self._observer is not None:
            self._observer.on_transition(
                TransitionObservedEvent(
                    customer_id=customer_id,
                    from_state=result.from_state,
                    to_state=result.to_state,
                    lifecycle_event=event,
                )
            )
        return result

    def trigger_edd_restriction(
        self,
        customer_id: str,
        amount: Decimal,  # I-01: Decimal ONLY
        entity_type: str = "INDIVIDUAL",
    ) -> TransitionResult | None:
        """Suspend customer when a transaction breaches the EDD threshold (I-04).

        Uses Decimal comparison throughout — never float (I-01).
        Returns the SUSPENDED TransitionResult if threshold exceeded,
        None if below threshold or transition invalid for current state.

        Raises:
            EddBreachError: informational — always paired with a returned result.
        """
        thresholds = get_thresholds(entity_type)
        if amount >= thresholds.edd_trigger:  # I-01: Decimal comparison
            result = self._engine.transition(customer_id, LifecycleEvent.SUSPEND)
            if result is not None:
                if self._observer is not None:
                    self._observer.on_edd_breach(
                        EddBreachObservedEvent(
                            customer_id=customer_id,
                            amount=_decimal_str(amount),
                            threshold=_decimal_str(thresholds.edd_trigger),
                            entity_type=entity_type,
                        )
                    )
                raise EddBreachError(
                    f"EDD threshold breached for {customer_id!r}: "
                    f"amount={amount} >= trigger={thresholds.edd_trigger} "
                    f"({entity_type}). Customer suspended (I-04)."
                )
            return result
        return None

    def notify_attribute_change(
        self,
        customer_id: str,
        event_type: BanxeEventType,
        triggered_by: str,
        previous_value: str,
        new_value: str,
    ) -> KycReTriggerEvent:
        """Record a KYC re-trigger event for attribute changes (ADR-028, G-KYC-01/02).

        JURISDICTION_CHANGED (CRITICAL): auto-suspends ACTIVE customers immediately.
        Publishes to event_bus if wired; always records pending retrigger.
        """
        retrigger = build_kyc_retrigger_event(
            event_type=event_type,
            customer_id=customer_id,
            triggered_by=triggered_by,
            previous_value=previous_value,
            new_value=new_value,
        )
        self._pending_retriggers[customer_id] = retrigger

        if self._event_bus is not None:
            self._event_bus.publish(
                DomainEvent.create(
                    event_type=event_type,
                    source_service="kyc_lifecycle",
                    payload={
                        "triggered_by": triggered_by,
                        "previous_value": previous_value,
                        "new_value": new_value,
                        "criticality": retrigger.criticality,
                        "gap_ref": retrigger.gap_ref,
                    },
                    customer_id=customer_id,
                )
            )

        # ADR-028 Step 5: emit KYC_REVERIFICATION_TRIGGERED audit event after
        # the bus publish. Wrapped in contextlib.suppress so an audit-sink
        # failure cannot break event delivery (defence-in-depth complementing
        # the ADR-027 BufferedAuditPort's own swallow).
        import contextlib

        with contextlib.suppress(Exception):
            emitter = self._audit_emitter
            if emitter is None:
                from services.kyc.factory import get_kyc_retrigger_audit_emitter

                emitter = get_kyc_retrigger_audit_emitter()
            trigger_type = _BANXE_EVENT_TO_TRIGGER_TYPE.get(event_type.value)
            if trigger_type is not None:
                emitter.emit(
                    customer_id=customer_id,
                    trigger_type=trigger_type,
                    trigger_payload={
                        "previous_value": previous_value,
                        "new_value": new_value,
                        "criticality": retrigger.criticality,
                        "gap_ref": retrigger.gap_ref,
                    },
                    requested_by=triggered_by,
                )

        if retrigger.criticality == "CRITICAL":
            if self._engine.get_state(customer_id) == CustomerState.ACTIVE:
                self._engine.transition(customer_id, LifecycleEvent.SUSPEND)

        return retrigger

    def get_pending_retrigger(self, customer_id: str) -> KycReTriggerEvent | None:
        """Return pending KYC re-trigger for customer, or None if none recorded."""
        return self._pending_retriggers.get(customer_id)

    def clear_pending_retrigger(self, customer_id: str) -> None:
        """Mark KYC re-verification as completed for customer."""
        self._pending_retriggers.pop(customer_id, None)

    def get_state(self, customer_id: str) -> CustomerState:
        return self._engine.get_state(customer_id)

    def get_history(self, customer_id: str) -> list[TransitionResult]:
        return self._engine.get_history(customer_id)
