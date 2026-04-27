"""
services/customer_lifecycle/fsm.py
KYC/EDD-gated Customer Lifecycle FSM (IL-KYC-01).

Wraps LifecycleEngine with guards:
  - KYC_PENDING → ACTIVE  : requires KYC APPROVED signal (KYCGuardPort)
  - ACTIVE → SUSPENDED    : triggered by EDD breach >£10k individual (I-04)
  - SUSPENDED → ACTIVE    : requires MLRO HITL L4 approval (I-27)
  - ACTIVE/DORMANT → CLOSED: requires FATCA/CRS reporting complete

Invariants: I-01 (Decimal), I-02 (jurisdictions), I-04 (EDD), I-27 (HITL L4).
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
from services.kyc.kyc_port import KYCStatus

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
    ) -> None:
        self._engine = engine or LifecycleEngine(InMemoryLifecycleStore())
        self._kyc: KYCGuardPort = kyc_guard or InMemoryKYCGuard()
        self._fatca_crs: FatcaCrsPort = fatca_crs or InMemoryFatcaCrsGuard()
        self._hitl: HITLLifecyclePort = hitl or InMemoryHITLLifecyclePort()

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
                raise KYCNotApprovedError(
                    f"Customer {customer_id!r} KYC status is {status.value!r}; "
                    "APPROVED required before activation."
                )

        # Guard: SUSPENDED → ACTIVE requires MLRO HITL L4 approval (I-27)
        if event == LifecycleEvent.ACTIVATE and current == CustomerState.SUSPENDED:
            if not self._hitl.has_mlro_approval(customer_id, _HITL_GATE_RESTRICTED_TO_ACTIVE):
                raise HITLRequiredError(
                    f"Customer {customer_id!r} requires MLRO L4 approval "
                    f"(gate={_HITL_GATE_RESTRICTED_TO_ACTIVE!r}) before reactivation (I-27)."
                )

        # Guard: CLOSE requires FATCA/CRS reporting complete
        if event == LifecycleEvent.CLOSE:
            if not self._fatca_crs.is_reporting_complete(customer_id):
                raise FatcaCrsIncompleteError(
                    f"Customer {customer_id!r} has outstanding FATCA/CRS reporting; "
                    "cannot close until reporting is complete."
                )

        return self._engine.transition(customer_id, event, country)

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
                raise EddBreachError(
                    f"EDD threshold breached for {customer_id!r}: "
                    f"amount={amount} >= trigger={thresholds.edd_trigger} "
                    f"({entity_type}). Customer suspended (I-04)."
                )
            return result
        return None

    def get_state(self, customer_id: str) -> CustomerState:
        return self._engine.get_state(customer_id)

    def get_history(self, customer_id: str) -> list[TransitionResult]:
        return self._engine.get_history(customer_id)
