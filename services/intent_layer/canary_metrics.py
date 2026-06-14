"""
services/intent_layer/canary_metrics.py — canary observability hooks
FU-2 Phase 5 — staging canary (notifications only) | banxe-emi-stack

A canary is only safe if it is observable. This module supplies the monitoring seam the
router calls on every gated decision, so an operator can watch the Phase-5 canary:

  • total canary intents seen (enabled-path resolutions reaching the gate),
  • how many were dispatched vs withheld (not-canary) vs withheld (high-risk),
  • and the dispatch error rate.

The router depends only on the :class:`CanaryObserver` Protocol (consistent with the
layer's injected-port design). Three implementations are provided:

  • :class:`NullCanaryObserver`  — default no-op (zero overhead, no behaviour change).
  • :class:`CounterCanaryObserver` — in-process counters for tests / a /metrics probe.
  • :class:`LoggingCanaryObserver` — structured ``logging`` records for log-based
    monitoring + alerting; carries only the correlation id + capability key + decision
    (R-SEC: never raw intent text or PII).

A :class:`FanOutCanaryObserver` composes several observers (e.g. log + counter) so a
deployment can both emit logs and expose counters.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import logging
from typing import Protocol, runtime_checkable

from services.intent_layer.canary import CanaryDecision, normalise_capability

logger = logging.getLogger("banxe.intent_layer.canary")


@runtime_checkable
class CanaryObserver(Protocol):
    """Sink for canary gate outcomes. Implementations MUST be side-effect-only —
    a misbehaving observer must never change routing behaviour."""

    def observe(
        self, *, decision: CanaryDecision, capability: str, correlation_id: str
    ) -> None: ...

    def observe_error(self, *, capability: str, correlation_id: str) -> None: ...


class NullCanaryObserver:
    """Default observer: records nothing. Keeps the router's behaviour unchanged when
    no monitoring is wired."""

    def observe(self, *, decision: CanaryDecision, capability: str, correlation_id: str) -> None:
        return None

    def observe_error(self, *, capability: str, correlation_id: str) -> None:
        return None


@dataclass
class CounterCanaryObserver:
    """In-process counters — the read surface for a /metrics probe or a test assertion.

    ``decisions`` counts gate outcomes by :class:`CanaryDecision`; ``errors`` counts
    dispatch failures. ``total`` is every gate hit (the canary-intent volume).
    """

    decisions: Counter[CanaryDecision] = field(default_factory=Counter)
    errors: int = 0

    def observe(self, *, decision: CanaryDecision, capability: str, correlation_id: str) -> None:
        self.decisions[decision] += 1

    def observe_error(self, *, capability: str, correlation_id: str) -> None:
        self.errors += 1

    @property
    def total(self) -> int:
        """Total gated canary intents seen."""
        return sum(self.decisions.values())

    @property
    def dispatched(self) -> int:
        return self.decisions[CanaryDecision.DISPATCH]

    @property
    def withheld(self) -> int:
        """Intents withheld for any reason (not-canary + high-risk)."""
        return (
            self.decisions[CanaryDecision.WITHHELD_NOT_CANARY]
            + self.decisions[CanaryDecision.WITHHELD_HIGH_RISK]
        )

    def snapshot(self) -> dict[str, int]:
        """A flat, JSON-friendly view for a metrics endpoint."""
        return {
            "canary_intents_total": self.total,
            "canary_dispatched": self.dispatched,
            "canary_withheld_not_canary": self.decisions[CanaryDecision.WITHHELD_NOT_CANARY],
            "canary_withheld_high_risk": self.decisions[CanaryDecision.WITHHELD_HIGH_RISK],
            "canary_errors": self.errors,
        }


class LoggingCanaryObserver:
    """Emits one structured log record per gate decision (and per dispatch error).

    R-SEC: only the correlation id, normalised capability key and decision are logged —
    never the free-form intent text or any PII. High-risk withholds log at WARNING so
    they surface in alerting; everything else is INFO/ERROR.
    """

    def observe(self, *, decision: CanaryDecision, capability: str, correlation_id: str) -> None:
        level = logging.WARNING if decision is CanaryDecision.WITHHELD_HIGH_RISK else logging.INFO
        logger.log(
            level,
            "intent_layer.canary decision=%s capability=%s correlation_id=%s",
            decision.value,
            normalise_capability(capability),
            correlation_id,
            extra={
                "event": "intent_layer.canary.decision",
                "decision": decision.value,
                "capability_key": normalise_capability(capability),
                "correlation_id": correlation_id,
            },
        )

    def observe_error(self, *, capability: str, correlation_id: str) -> None:
        logger.error(
            "intent_layer.canary dispatch_error capability=%s correlation_id=%s",
            normalise_capability(capability),
            correlation_id,
            extra={
                "event": "intent_layer.canary.error",
                "capability_key": normalise_capability(capability),
                "correlation_id": correlation_id,
            },
        )


@dataclass
class FanOutCanaryObserver:
    """Composes several observers — e.g. log + counter — behind one port."""

    observers: tuple[CanaryObserver, ...]

    def observe(self, *, decision: CanaryDecision, capability: str, correlation_id: str) -> None:
        for obs in self.observers:
            obs.observe(decision=decision, capability=capability, correlation_id=correlation_id)

    def observe_error(self, *, capability: str, correlation_id: str) -> None:
        for obs in self.observers:
            obs.observe_error(capability=capability, correlation_id=correlation_id)


__all__ = [
    "CanaryObserver",
    "CounterCanaryObserver",
    "FanOutCanaryObserver",
    "LoggingCanaryObserver",
    "NullCanaryObserver",
]
