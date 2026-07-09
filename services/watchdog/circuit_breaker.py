"""GAP-A — Circuit breaker (CLOSED/OPEN/HALF_OPEN) + ShellCommandPort.

Thresholds injected from watchdog.yaml via GuardedActionExecutor — no hardcoding.
I-27: when OPEN → ESCALATE immediately (no partial execution).
"""

from __future__ import annotations

from enum import Enum
from typing import Protocol


class CBState(Enum):
    """Circuit breaker state machine."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreakerState:
    """Per-action circuit breaker with exponential backoff.

    CLOSED → (failures ≥ max_attempts) → OPEN → (quarantine expires) → HALF_OPEN →
    (probe success) → CLOSED  OR  (probe failure) → OPEN (longer backoff).
    """

    def __init__(self) -> None:
        self.attempts: int = 0
        self.quarantine_until: float = 0.0
        self._state: CBState = CBState.CLOSED

    def get_state(self, now: float) -> CBState:
        """Return effective state at clock time `now`."""
        if self._state == CBState.OPEN and now >= self.quarantine_until:
            return CBState.HALF_OPEN
        return self._state

    def is_blocked(self, now: float) -> bool:
        """True when the circuit is OPEN (probe not yet allowed)."""
        return self.get_state(now) == CBState.OPEN

    def record_failure(
        self,
        now: float,
        max_attempts: int,
        backoff_base_s: float,
        max_quarantine_s: float,
    ) -> None:
        """Record a dispatch or verify failure; open circuit when threshold reached."""
        self.attempts += 1
        if self.attempts >= max_attempts:
            exponent = self.attempts - max_attempts + 1
            delay = min(backoff_base_s * (2**exponent), max_quarantine_s)
            self.quarantine_until = now + delay
            self._state = CBState.OPEN

    def record_success(self) -> None:
        """Reset to CLOSED on successful action."""
        self.attempts = 0
        self.quarantine_until = 0.0
        self._state = CBState.CLOSED


class ShellCommandPort(Protocol):
    """Protocol for executing shell commands (injected; never module-level)."""

    async def run(self, cmd: list[str], *, timeout: float = 30.0) -> tuple[int, str]: ...


class InMemoryShellPort:
    """Stub for unit tests — returns pre-configured responses by command string."""

    def __init__(
        self,
        responses: dict[str, tuple[int, str]] | None = None,
        default: tuple[int, str] = (0, ""),
    ) -> None:
        self._responses: dict[str, tuple[int, str]] = dict(responses or {})
        self._default = default
        self.calls: list[list[str]] = []

    async def run(self, cmd: list[str], *, timeout: float = 30.0) -> tuple[int, str]:
        self.calls.append(list(cmd))
        key = " ".join(cmd)
        return self._responses.get(key, self._default)


__all__ = ["CBState", "CircuitBreakerState", "InMemoryShellPort", "ShellCommandPort"]
