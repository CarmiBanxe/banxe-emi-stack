"""
services/ato_prevention/session_manager.py
SessionManagerPort Protocol + InMemorySessionManager (IL-FRAUD-02).

I-24: Session state changes are append-only audit events.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Protocol


class SessionState(str, Enum):
    """Session states."""

    ACTIVE = "ACTIVE"
    STEP_UP_REQUIRED = "STEP_UP_REQUIRED"
    LOCKED = "LOCKED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class SessionEvent:
    """Immutable session state change event (I-24)."""

    session_id: str
    customer_id: str
    old_state: SessionState | None
    new_state: SessionState
    reason: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class SessionManagerPort(Protocol):
    """Port for managing session states."""

    def get_state(self, session_id: str) -> SessionState | None: ...

    def set_state(
        self, session_id: str, customer_id: str, state: SessionState, reason: str
    ) -> SessionEvent: ...

    def get_events(self, customer_id: str) -> list[SessionEvent]: ...


class InMemorySessionManager:
    """In-memory session manager for tests."""

    def __init__(self) -> None:
        self._states: dict[str, SessionState] = {}
        self._customer_map: dict[str, str] = {}  # session_id → customer_id
        self._events: list[SessionEvent] = []

    def get_state(self, session_id: str) -> SessionState | None:
        return self._states.get(session_id)

    def set_state(
        self,
        session_id: str,
        customer_id: str,
        state: SessionState,
        reason: str,
    ) -> SessionEvent:
        old_state = self._states.get(session_id)
        self._states[session_id] = state
        self._customer_map[session_id] = customer_id
        event = SessionEvent(
            session_id=session_id,
            customer_id=customer_id,
            old_state=old_state,
            new_state=state,
            reason=reason,
        )
        self._events.append(event)
        return event

    def get_events(self, customer_id: str) -> list[SessionEvent]:
        return [e for e in self._events if e.customer_id == customer_id]

    @property
    def all_events(self) -> list[SessionEvent]:
        return list(self._events)
