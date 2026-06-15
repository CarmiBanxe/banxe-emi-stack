"""
tests/test_intent_layer/test_observability.py — FU-2 Phase 6 canary observability.

Validates the metrics/logging hooks added for the ADR-049 L1 Intent Layer *canary*
(Notifications in staging) and the S1 LLM-gateway seam, with NO live gateway and NO
metrics backend — every dependency is an in-memory double:

  * CanaryObserver emits the request/latency counters with the expected labels, an
    error counter on a rejected dispatch, and a guardrail-trigger counter on a
    compliance FAIL/ESCALATE or a high-risk flag.
  * InstrumentedLLMClassifier times a gateway call and counts gateway errors, while
    staying transparent (returns the delegate's result, re-raises its errors).
  * The CANARY_METRICS selection seam defaults to the no-op sink and fails closed.
  * At the HTTP surface: when the canary is ENABLED a ``banxe.intent_layer.canary``
    log fires for a Notifications intent; when DISABLED (dark/prod) NOTHING is
    emitted — the dark-mode no-side-effect contract is preserved.
"""

from __future__ import annotations

import logging

import pytest

from services.intent_layer.observability import (
    ERRORS_TOTAL,
    GATEWAY_ERRORS_TOTAL,
    GATEWAY_LATENCY_MS,
    GUARDRAIL_TRIGGERS_TOTAL,
    LATENCY_MS,
    REQUESTS_TOTAL,
    CanaryEvent,
    CanaryObserver,
    InMemoryCanaryMetrics,
    InstrumentedLLMClassifier,
    NullCanaryMetrics,
    canary_env,
)
from services.intent_layer.ports import LLMClassification, NullLLMClassifier

CANARY_LOGGER = "banxe.intent_layer.canary"


# ── CanaryObserver: counters + labels ────────────────────────────────────────────


def _observe(event: CanaryEvent, env: str = "staging") -> InMemoryCanaryMetrics:
    metrics = InMemoryCanaryMetrics()
    CanaryObserver(metrics, env=env).observe(event)
    return metrics


def test_observer_emits_request_and_latency_with_labels():
    """A successful dispatch increments requests_total{capability,env,disposition}
    and observes the latency — the canary's traffic/latency signals."""
    metrics = _observe(
        CanaryEvent(
            capability="Notifications",
            disposition="DISPATCHED",
            latency_ms=12.5,
            success=True,
        )
    )
    assert (
        metrics.counter_total(
            REQUESTS_TOTAL, capability="Notifications", env="staging", disposition="DISPATCHED"
        )
        == 1
    )
    assert metrics.observations(LATENCY_MS) == [12.5]
    # A clean PASS dispatch is neither an error nor a guardrail trigger.
    assert metrics.counter_total(ERRORS_TOTAL) == 0
    assert metrics.counter_total(GUARDRAIL_TRIGGERS_TOTAL) == 0


def test_observer_counts_error_on_rejected_dispatch():
    """A failed dispatch increments errors_total with the reason label."""
    metrics = _observe(
        CanaryEvent(
            capability="Notifications",
            disposition="DISPATCHED",
            latency_ms=4.0,
            success=False,
            error_reason="dispatch_rejected",
        )
    )
    assert metrics.counter_total(ERRORS_TOTAL, reason="dispatch_rejected") == 1


@pytest.mark.parametrize(
    ("compliance_result", "high_risk", "expected_reason"),
    [
        ("FAIL", False, "compliance_fail"),
        ("ESCALATE", False, "compliance_escalate"),
        ("PASS", True, "high_risk"),
    ],
)
def test_observer_counts_guardrail_triggers(compliance_result, high_risk, expected_reason):
    """A compliance FAIL/ESCALATE or a high-risk flag is a guardrail trigger — the
    safety-violation signal the canary watches for spikes."""
    metrics = _observe(
        CanaryEvent(
            capability="Notifications",
            disposition="DISPATCHED",
            latency_ms=1.0,
            success=True,
            compliance_result=compliance_result,
            high_risk_flag=high_risk,
        )
    )
    assert metrics.counter_total(GUARDRAIL_TRIGGERS_TOTAL, reason=expected_reason) == 1


def test_observer_clean_pass_triggers_no_guardrail():
    """A PASS with no high-risk flag emits zero guardrail triggers."""
    metrics = _observe(
        CanaryEvent(
            capability="Notifications",
            disposition="DISPATCHED",
            latency_ms=1.0,
            success=True,
            compliance_result="PASS",
            high_risk_flag=False,
        )
    )
    assert metrics.counter_total(GUARDRAIL_TRIGGERS_TOTAL) == 0


def test_observer_logs_structured_fields(caplog):
    """The structured canary log carries env/capability/disposition/compliance/
    high_risk — the always-on observable that needs no metrics backend."""
    with caplog.at_level(logging.INFO, logger=CANARY_LOGGER):
        CanaryObserver(NullCanaryMetrics(), env="staging").observe(
            CanaryEvent(
                capability="Notifications",
                disposition="DISPATCHED",
                latency_ms=2.0,
                success=True,
                compliance_result="PASS",
            )
        )
    records = [r for r in caplog.records if r.name == CANARY_LOGGER]
    assert len(records) == 1
    msg = records[0].getMessage()
    assert "capability=Notifications" in msg
    assert "env=staging" in msg
    assert "disposition=DISPATCHED" in msg


# ── LLM-gateway instrumentation ───────────────────────────────────────────────────


class _StubGateway:
    """LLMClassifierPort double that returns a fixed match (a 'live' gateway)."""

    def classify(self, intent_text, candidates):
        return LLMClassification(matched_intent="get-notified", confidence=0.95)


class _BoomGateway:
    """LLMClassifierPort double that always fails — a gateway error."""

    def classify(self, intent_text, candidates):
        raise TimeoutError("gateway unreachable")


def test_gateway_instrumentation_times_successful_call():
    """A successful gateway call records a latency observation and is transparent."""
    metrics = InMemoryCanaryMetrics()
    classifier = InstrumentedLLMClassifier(_StubGateway(), metrics, env="staging")

    result = classifier.classify("ping me", [])

    assert result is not None and result.matched_intent == "get-notified"
    assert len(metrics.observations(GATEWAY_LATENCY_MS)) == 1
    assert metrics.counter_total(GATEWAY_ERRORS_TOTAL) == 0


def test_gateway_instrumentation_counts_and_reraises_errors():
    """A gateway failure increments gateway_errors_total{reason} and re-raises."""
    metrics = InMemoryCanaryMetrics()
    classifier = InstrumentedLLMClassifier(_BoomGateway(), metrics, env="staging")

    with pytest.raises(TimeoutError):
        classifier.classify("ping me", [])

    assert metrics.counter_total(GATEWAY_ERRORS_TOTAL, reason="TimeoutError") == 1
    assert metrics.observations(GATEWAY_LATENCY_MS) == []


def test_gateway_instrumentation_over_null_is_inert():
    """Wrapping the Null classifier records a (fast) latency sample and abstains —
    proving the wrap is transparent over the default no-LLM seam."""
    metrics = InMemoryCanaryMetrics()
    classifier = InstrumentedLLMClassifier(NullLLMClassifier(), metrics)
    assert classifier.classify("anything", []) is None
    assert len(metrics.observations(GATEWAY_LATENCY_MS)) == 1


# ── Env label + metrics selection seam ────────────────────────────────────────────


def test_canary_env_reads_banxe_env():
    assert canary_env(env={"BANXE_ENV": "Staging"}) == "staging"
    assert canary_env(env={}) == "unknown"


def test_get_canary_metrics_seam(monkeypatch):
    """Default → no-op sink; ``inmemory`` → recordable; anything else fails closed."""
    from api.routers.intent import get_canary_metrics

    monkeypatch.delenv("CANARY_METRICS", raising=False)
    assert isinstance(get_canary_metrics(), NullCanaryMetrics)

    monkeypatch.setenv("CANARY_METRICS", "inmemory")
    assert isinstance(get_canary_metrics(), InMemoryCanaryMetrics)

    monkeypatch.setenv("CANARY_METRICS", "prometheus")
    with pytest.raises(ValueError, match="CANARY_METRICS"):
        get_canary_metrics()


# ── HTTP surface: emitted when enabled, silent when dark ──────────────────────────


def _post_intent(monkeypatch, *, enabled: bool, caplog):
    from fastapi.testclient import TestClient

    from api.main import app

    monkeypatch.setenv("INTENT_LAYER_ENABLED", "true" if enabled else "false")
    monkeypatch.setenv("BANXE_ENV", "staging")
    monkeypatch.setenv("CANARY_METRICS", "inmemory")
    client = TestClient(app)
    with caplog.at_level(logging.INFO, logger=CANARY_LOGGER):
        resp = client.post(
            "/v1/intent",
            json={"intent_text": "notifications", "correlation_id": f"obs-{enabled}"},
        )
    assert resp.status_code == 200
    return resp.json(), [r for r in caplog.records if r.name == CANARY_LOGGER]


def test_http_canary_enabled_emits_log(monkeypatch, caplog):
    """ENABLED: a Notifications intent produces a canary log (a metrics/logging hook
    fired) tagged with the Notifications capability + staging env."""
    body, records = _post_intent(monkeypatch, enabled=True, caplog=caplog)
    assert body["enabled"] is True
    assert len(records) == 1
    msg = records[0].getMessage()
    assert "capability=Notifications" in msg
    assert "env=staging" in msg


def test_http_canary_disabled_emits_nothing(monkeypatch, caplog):
    """DISABLED (dark/prod): NOT_ENABLED envelope and NO canary log — the
    no-side-effect dark-mode contract holds for observability too."""
    body, records = _post_intent(monkeypatch, enabled=False, caplog=caplog)
    assert body["enabled"] is False
    assert body["disposition"] == "NOT_ENABLED"
    assert records == []
