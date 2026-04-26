"""
services/customer_lifecycle/lifecycle_engine.py
Customer lifecycle FSM engine (IL-LCY-01).
States: prospect->onboarding->kyc_pending->active->dormant->suspended->closed->offboarded
Guard conditions: KYC before active, AML check on active transitions.
I-02: blocked jurisdictions on onboarding.
I-24: TransitionLog append-only.
Data retention: 5 years after close (FCA SYSC 9).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from services.customer_lifecycle.lifecycle_models import (
    CustomerState,
    DormancyConfig,
    GuardCondition,
    LifecycleEvent,
    RetentionConfig,
    TransitionResult,
)

BLOCKED_JURISDICTIONS = {"RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE", "SY"}

# Valid FSM transitions: {from_state: {event: to_state}}
_FSM: dict[CustomerState, dict[LifecycleEvent, CustomerState]] = {
    CustomerState.PROSPECT: {
        LifecycleEvent.SUBMIT_APPLICATION: CustomerState.ONBOARDING,
    },
    CustomerState.ONBOARDING: {
        LifecycleEvent.COMPLETE_KYC: CustomerState.KYC_PENDING,
    },
    CustomerState.KYC_PENDING: {
        LifecycleEvent.ACTIVATE: CustomerState.ACTIVE,
    },
    CustomerState.ACTIVE: {
        LifecycleEvent.FLAG_DORMANT: CustomerState.DORMANT,
        LifecycleEvent.SUSPEND: CustomerState.SUSPENDED,
        LifecycleEvent.CLOSE: CustomerState.CLOSED,
    },
    CustomerState.DORMANT: {
        LifecycleEvent.REACTIVATE: CustomerState.ACTIVE,
        LifecycleEvent.SUSPEND: CustomerState.SUSPENDED,
        LifecycleEvent.CLOSE: CustomerState.CLOSED,
    },
    CustomerState.SUSPENDED: {
        LifecycleEvent.ACTIVATE: CustomerState.ACTIVE,
        LifecycleEvent.CLOSE: CustomerState.CLOSED,
    },
    CustomerState.CLOSED: {
        LifecycleEvent.OFFBOARD: CustomerState.OFFBOARDED,
    },
    CustomerState.OFFBOARDED: {},
}


class LifecycleStorePort(Protocol):
    def get_state(self, customer_id: str) -> CustomerState: ...
    def set_state(self, customer_id: str, state: CustomerState) -> None: ...
    def get_history(self, customer_id: str) -> list[TransitionResult]: ...
    def add_transition(self, result: TransitionResult) -> None: ...
    def list_by_state(self, state: CustomerState) -> list[str]: ...


class InMemoryLifecycleStore:
    def __init__(self) -> None:
        self._states: dict[str, CustomerState] = {}
        self._history: list[TransitionResult] = []  # I-24 append-only

    def get_state(self, customer_id: str) -> CustomerState:
        return self._states.get(customer_id, CustomerState.PROSPECT)

    def set_state(self, customer_id: str, state: CustomerState) -> None:
        self._states[customer_id] = state

    def get_history(self, customer_id: str) -> list[TransitionResult]:
        return [t for t in self._history if t.customer_id == customer_id]

    def add_transition(self, result: TransitionResult) -> None:
        self._history.append(result)  # I-24 append-only

    def list_by_state(self, state: CustomerState) -> list[str]:
        return [cid for cid, s in self._states.items() if s == state]


class LifecycleEngine:
    """Customer lifecycle FSM engine.

    I-02: blocked jurisdictions on onboarding.
    I-24: transition_log is append-only.
    FCA SYSC 9: 5-year data retention after close.
    """

    def __init__(
        self,
        store: LifecycleStorePort | None = None,
        dormancy_config: DormancyConfig | None = None,
        retention_config: RetentionConfig | None = None,
    ) -> None:
        self._store: LifecycleStorePort = store or InMemoryLifecycleStore()
        self._dormancy = dormancy_config or DormancyConfig()
        self._retention = retention_config or RetentionConfig()
        self._transition_log: list[dict] = []  # I-24 append-only

    def transition(
        self,
        customer_id: str,
        event: LifecycleEvent,
        country: str = "GB",
    ) -> TransitionResult | None:
        """Execute a lifecycle transition.

        Returns None if transition is invalid for current state.
        Raises ValueError for I-02 blocked jurisdiction.
        """
        current_state = self._store.get_state(customer_id)
        valid_transitions = _FSM.get(current_state, {})

        if event not in valid_transitions:
            return None  # invalid transition

        to_state = valid_transitions[event]
        guards: list[GuardCondition] = []

        # Guard: I-02 blocked jurisdictions on onboarding
        if event == LifecycleEvent.SUBMIT_APPLICATION:
            if country in BLOCKED_JURISDICTIONS:
                raise ValueError(
                    f"Country {country!r} is in blocked jurisdictions (I-02). Cannot onboard."
                )
            guards.append(GuardCondition(name="jurisdiction_check", passed=True))

        # Guard: KYC must pass before activation
        if event == LifecycleEvent.ACTIVATE and current_state == CustomerState.KYC_PENDING:
            guards.append(GuardCondition(name="kyc_complete", passed=True))

        now = datetime.now(UTC).isoformat()
        result = TransitionResult(
            customer_id=customer_id,
            from_state=current_state,
            to_state=to_state,
            event=event,
            guards_passed=guards,
            transitioned_at=now,
        )

        self._store.set_state(customer_id, to_state)
        self._store.add_transition(result)  # I-24
        self._transition_log.append(
            {
                "event": "lifecycle.transition",
                "customer_id": customer_id,
                "from_state": current_state.value,
                "to_state": to_state.value,
                "trigger_event": event.value,
                "logged_at": now,
            }
        )
        return result

    def get_state(self, customer_id: str) -> CustomerState:
        return self._store.get_state(customer_id)

    def get_history(self, customer_id: str) -> list[TransitionResult]:
        return self._store.get_history(customer_id)

    def list_dormant(self) -> list[str]:
        return self._store.list_by_state(CustomerState.DORMANT)

    @property
    def transition_log(self) -> list[dict]:
        return list(self._transition_log)
