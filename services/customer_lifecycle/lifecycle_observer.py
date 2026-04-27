"""
services/customer_lifecycle/lifecycle_observer.py
Protocol DI observer for KYC lifecycle state transitions (IL-OBS-01).

Emits structured events on:
  - Successful state transitions
  - Guard failures (KYC, HITL L4, FATCA/CRS)
  - EDD threshold breaches (I-04)

I-01: all monetary amounts stored as Decimal strings (never float).
I-24: event logs are append-only — no update or delete.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from services.customer_lifecycle.lifecycle_models import CustomerState, LifecycleEvent


@dataclass(frozen=True)
class TransitionObservedEvent:
    customer_id: str
    from_state: CustomerState
    to_state: CustomerState
    lifecycle_event: LifecycleEvent
    occurred_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass(frozen=True)
class GuardFailureEvent:
    customer_id: str
    guard_type: str  # "KYC_NOT_APPROVED" | "HITL_REQUIRED" | "FATCA_CRS_INCOMPLETE"
    detail: str
    occurred_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass(frozen=True)
class EddBreachObservedEvent:
    customer_id: str
    amount: str  # Decimal as string (I-01, I-05)
    threshold: str  # Decimal as string (I-01, I-05)
    entity_type: str
    occurred_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class LifecycleObserverPort(Protocol):
    """Narrow port for observing lifecycle state transitions (I-24)."""

    def on_transition(self, event: TransitionObservedEvent) -> None: ...

    def on_guard_failure(self, event: GuardFailureEvent) -> None: ...

    def on_edd_breach(self, event: EddBreachObservedEvent) -> None: ...


class InMemoryLifecycleObserver:
    """Append-only in-memory observer for tests (I-24).

    Lists exposed as read-only copies — callers cannot mutate internal state.
    """

    def __init__(self) -> None:
        self._transitions: list[TransitionObservedEvent] = []
        self._guard_failures: list[GuardFailureEvent] = []
        self._edd_breaches: list[EddBreachObservedEvent] = []

    def on_transition(self, event: TransitionObservedEvent) -> None:
        self._transitions.append(event)

    def on_guard_failure(self, event: GuardFailureEvent) -> None:
        self._guard_failures.append(event)

    def on_edd_breach(self, event: EddBreachObservedEvent) -> None:
        self._edd_breaches.append(event)

    @property
    def transitions(self) -> list[TransitionObservedEvent]:
        return list(self._transitions)

    @property
    def guard_failures(self) -> list[GuardFailureEvent]:
        return list(self._guard_failures)

    @property
    def edd_breaches(self) -> list[EddBreachObservedEvent]:
        return list(self._edd_breaches)

    def total_events(self) -> int:
        return len(self._transitions) + len(self._guard_failures) + len(self._edd_breaches)


def _decimal_str(value: Decimal) -> str:
    """Serialise a Decimal as a plain string for I-01/I-05 compliance."""
    return str(value)
