"""Metrics + alert hook (ADR-030 §9). Prometheus-style counters with an InMemory
sink for the sandbox. Alert rule (doc): ``agent_halt_triggered > 0`` → notify
(PagerDuty adapter = Outcome-C stub).
"""

from __future__ import annotations

from typing import Protocol

COUNTERS = ("agent_halt_triggered", "decision_refused", "budget_exceeded")

# Alert rules (documented; wire to Prometheus/Alertmanager in production).
ALERT_RULES = {
    "agent_halt_triggered": "> 0  → PAGE (RED agent halted)",
    "budget_exceeded": "> 0  → WARN (agent refused on budget)",
    "decision_refused": "rate spike → WARN (investigate refusals)",
}


class MetricsPort(Protocol):
    def inc(self, counter: str, agent_id: str, n: int = 1) -> None: ...
    def value(self, counter: str, agent_id: str) -> int: ...


class InMemoryMetrics:
    """Sandbox sink — labelled by (counter, agent_id)."""

    def __init__(self) -> None:
        self._c: dict[tuple[str, str], int] = {}

    def inc(self, counter: str, agent_id: str, n: int = 1) -> None:
        if counter not in COUNTERS:
            raise ValueError(f"unknown counter {counter!r}")
        self._c[(counter, agent_id)] = self._c.get((counter, agent_id), 0) + n

    def value(self, counter: str, agent_id: str) -> int:
        return self._c.get((counter, agent_id), 0)

    def snapshot(self) -> dict[tuple[str, str], int]:
        return dict(self._c)


class PagerDutyAlerter:
    """Production alert adapter (Outcome-C)."""

    def notify(self, rule: str, agent_id: str) -> None:
        raise NotImplementedError(
            "Outcome-C: POST to the PagerDuty Events API for the RED-agent alert.")
