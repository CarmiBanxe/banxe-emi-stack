"""
services/intent_layer/observability.py — L1 Intent Layer canary + gateway observability
IL-FU2-OBSERVABILITY-2026-06-14 | banxe-emi-stack (FU-2 Phase 6)

Safety/observability instrumentation for the ADR-049 L1 Intent Layer *canary* (the
Notifications-in-staging path) and the S1 LLM-gateway calls it makes. This is the
seam that turns "is the canary behaving?" into concrete, queryable signals BEFORE the
canary is widened beyond Notifications.

DESIGN (banking-safe, additive, dependency-free):

  * Metrics flow through a :class:`CanaryMetricsPort` (Protocol DI), exactly like the
    ARL :class:`TelemetryPort`. The DEFAULT is :class:`NullCanaryMetrics` (no-op) so
    importing/constructing the observer is free and never reaches a metrics backend.
    Tests inject :class:`InMemoryCanaryMetrics`; a real Prometheus/StatsD/ClickHouse
    port is the operator runtime step (no new hard dependency is added here).

  * Structured logs go to the ``banxe.intent_layer.canary`` logger (and gateway calls
    to ``banxe.llm_gateway``). Logs need NO backend, so they are the always-on
    observable even when no metrics sink is wired.

  * Emission is GATED on the canary actually running. The router only invokes the
    observer when the disposition is NOT ``NOT_ENABLED`` — so a dark/prod deployment
    (INTENT_LAYER_ENABLED=false → NOT_ENABLED) emits NOTHING. Gating on "enabled"
    *is* gating on staging, because the canary is only enabled in staging. This keeps
    prod free of canary noise without a second flag.

R-SEC: only opaque governance labels are emitted — env, capability, disposition,
compliance result, a coarse high-risk boolean, an opaque tenant handle and the
correlation id. NEVER intent text, PII, secrets, or a raw subject identity.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import os
import time
from typing import Protocol, runtime_checkable

from services.intent_layer.models import IntentDefinition
from services.intent_layer.ports import LLMClassification, LLMClassifierPort

canary_logger = logging.getLogger("banxe.intent_layer.canary")
gateway_logger = logging.getLogger("banxe.llm_gateway")

# ── Metric names (stable label keys — keep in lockstep with the dashboards) ───────

REQUESTS_TOTAL = "intent_layer_canary_requests_total"
ERRORS_TOTAL = "intent_layer_canary_errors_total"
LATENCY_MS = "intent_layer_canary_latency_ms"
GUARDRAIL_TRIGGERS_TOTAL = "intent_layer_canary_guardrail_triggers_total"
GATEWAY_LATENCY_MS = "llm_gateway_request_latency_ms"
GATEWAY_ERRORS_TOTAL = "llm_gateway_errors_total"

CANARY_ENV_ENV = "BANXE_ENV"


def canary_env(env: dict[str, str] | None = None) -> str:
    """Deployment label for canary metrics. Reads ``BANXE_ENV`` (e.g. ``staging``);
    ``unknown`` when unset so an unlabelled emit is visible rather than silently
    masquerading as prod. Injectable env for deterministic tests."""
    source = env if env is not None else os.environ
    return (source.get(CANARY_ENV_ENV) or "unknown").strip().lower() or "unknown"


# ── Metrics port (Protocol DI) ────────────────────────────────────────────────────


@runtime_checkable
class CanaryMetricsPort(Protocol):
    """Sink for canary/gateway metrics. Implementations are wired at the composition
    root; the layer depends only on this interface (no Prometheus import here)."""

    def incr(self, name: str, *, labels: dict[str, str], value: int = 1) -> None: ...

    def observe(self, name: str, value: float, *, labels: dict[str, str]) -> None: ...


class NullCanaryMetrics:
    """Default metrics port: discards everything. Lets the observer be constructed and
    exercised with zero metrics-backend dependency (structured logs still fire)."""

    def incr(self, name: str, *, labels: dict[str, str], value: int = 1) -> None:
        return None

    def observe(self, name: str, value: float, *, labels: dict[str, str]) -> None:
        return None


@dataclass(frozen=True)
class MetricSample:
    """One recorded metric point (diagnostics / tests)."""

    name: str
    kind: str  # "counter" | "observation"
    value: float
    labels: dict[str, str]


class InMemoryCanaryMetrics:
    """In-memory metrics port for tests and local development — records every sample
    so assertions can check the exact name/labels/value emitted."""

    def __init__(self) -> None:
        self.samples: list[MetricSample] = []

    def incr(self, name: str, *, labels: dict[str, str], value: int = 1) -> None:
        self.samples.append(MetricSample(name, "counter", float(value), dict(labels)))

    def observe(self, name: str, value: float, *, labels: dict[str, str]) -> None:
        self.samples.append(MetricSample(name, "observation", float(value), dict(labels)))

    def counter_total(self, name: str, **label_filter: str) -> float:
        """Sum of counter ``name`` over samples matching every label in ``label_filter``."""
        return sum(
            s.value
            for s in self.samples
            if s.name == name
            and s.kind == "counter"
            and all(s.labels.get(k) == v for k, v in label_filter.items())
        )

    def observations(self, name: str) -> list[float]:
        return [s.value for s in self.samples if s.name == name and s.kind == "observation"]


# ── Canary disposition observer ────────────────────────────────────────────────────


@dataclass(frozen=True)
class CanaryEvent:
    """The auditable, PII-minimised summary of one canary disposition."""

    capability: str
    disposition: str
    latency_ms: float
    success: bool
    compliance_result: str = "N/A"
    high_risk_flag: bool = False
    error_reason: str | None = None
    tenant: str = "unknown"  # opaque handle; reserved for multi-tenant routing (never PII)
    correlation_id: str | None = None


class CanaryObserver:
    """Emits structured logs + metrics for one canary disposition. Constructed per
    request at the composition root; the metrics port defaults to the no-op sink."""

    def __init__(self, metrics: CanaryMetricsPort | None = None, *, env: str | None = None) -> None:
        self._metrics: CanaryMetricsPort = metrics if metrics is not None else NullCanaryMetrics()
        self._env = env if env is not None else canary_env()

    def observe(self, event: CanaryEvent) -> None:
        """Record one canary disposition. Call ONLY when the canary actually ran
        (disposition != NOT_ENABLED); dark/prod paths must not reach here."""
        base = {"capability": event.capability, "env": self._env}

        self._metrics.incr(REQUESTS_TOTAL, labels={**base, "disposition": event.disposition})
        self._metrics.observe(LATENCY_MS, event.latency_ms, labels=base)

        if not event.success:
            reason = event.error_reason or "unknown"
            self._metrics.incr(ERRORS_TOTAL, labels={**base, "reason": reason})

        guardrail = _guardrail_reason(event.compliance_result, event.high_risk_flag)
        if guardrail is not None:
            self._metrics.incr(GUARDRAIL_TRIGGERS_TOTAL, labels={**base, "reason": guardrail})

        canary_logger.info(
            "intent_layer.canary disposition=%s capability=%s env=%s outcome=%s "
            "compliance=%s high_risk=%s latency_ms=%.1f tenant=%s correlation_id=%s%s",
            event.disposition,
            event.capability,
            self._env,
            "success" if event.success else "error",
            event.compliance_result,
            str(event.high_risk_flag).lower(),
            event.latency_ms,
            event.tenant,
            event.correlation_id,
            f" guardrail={guardrail}" if guardrail else "",
        )


def _guardrail_reason(compliance_result: str, high_risk_flag: bool) -> str | None:
    """Map a disposition's safety signals to a guardrail-trigger reason, or None.

    A guardrail trigger is a compliance gate that did NOT cleanly PASS, or a
    high-risk flag — the spikes the canary watches before widening scope."""
    result = (compliance_result or "").upper()
    if result == "FAIL":
        return "compliance_fail"
    if result == "ESCALATE":
        return "compliance_escalate"
    if high_risk_flag:
        return "high_risk"
    return None


# ── LLM-gateway call instrumentation ────────────────────────────────────────────────


class InstrumentedLLMClassifier(LLMClassifierPort):
    """Decorates an :class:`LLMClassifierPort` (the S1 gateway seam) with latency +
    error metrics and structured gateway logs. Transparent: it returns the delegate's
    result and re-raises its errors after recording them, so behaviour is unchanged.

    Wrapping the Null classifier is inert — ``classify`` is only consulted when
    deterministic matching fails AND the layer is enabled, so dark mode never times a
    call. A real gateway adapter is injected in the delegate's place when live."""

    def __init__(
        self,
        delegate: LLMClassifierPort,
        metrics: CanaryMetricsPort | None = None,
        *,
        env: str | None = None,
    ) -> None:
        self._delegate = delegate
        self._metrics: CanaryMetricsPort = metrics if metrics is not None else NullCanaryMetrics()
        self._env = env if env is not None else canary_env()

    def classify(
        self, intent_text: str, candidates: list[IntentDefinition]
    ) -> LLMClassification | None:
        labels = {"env": self._env}
        start = time.monotonic()
        try:
            result = self._delegate.classify(intent_text, candidates)
        except Exception as exc:
            self._metrics.incr(
                GATEWAY_ERRORS_TOTAL, labels={**labels, "reason": type(exc).__name__}
            )
            gateway_logger.warning(
                "llm_gateway call failed env=%s error=%s", self._env, type(exc).__name__
            )
            raise
        latency_ms = (time.monotonic() - start) * 1000
        self._metrics.observe(GATEWAY_LATENCY_MS, latency_ms, labels=labels)
        gateway_logger.info(
            "llm_gateway call env=%s latency_ms=%.1f matched=%s",
            self._env,
            latency_ms,
            "yes" if result is not None else "no",
        )
        return result


__all__ = [
    "CANARY_ENV_ENV",
    "ERRORS_TOTAL",
    "GATEWAY_ERRORS_TOTAL",
    "GATEWAY_LATENCY_MS",
    "GUARDRAIL_TRIGGERS_TOTAL",
    "LATENCY_MS",
    "REQUESTS_TOTAL",
    "CanaryEvent",
    "CanaryMetricsPort",
    "CanaryObserver",
    "InMemoryCanaryMetrics",
    "InstrumentedLLMClassifier",
    "MetricSample",
    "NullCanaryMetrics",
    "canary_env",
]
