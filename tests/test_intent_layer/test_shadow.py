"""
tests/test_intent_layer/test_shadow.py — FU-2 Phase 8 production shadow-mode.

Covers ``services/intent_layer/shadow.py``: the production-gated, flag-gated, sampled
shadow pipeline that mirrors a prod intent through classify+route with a NON-ACTING
dispatcher, and logs/compares the result against the mechanistic baseline. The env is
injected (no os.environ), so every gate case is deterministic, and an exploding
dispatcher proves a high-risk intent never reaches a live action.
"""

from __future__ import annotations

import pytest

from services.intent_layer.observability import InMemoryCanaryMetrics
from services.intent_layer.ports import AgentDispatchPort, DispatchReceipt, DispatchRequest
from services.intent_layer.shadow import (
    SHADOW_ERRORS_TOTAL,
    SHADOW_MISMATCH_TOTAL,
    SHADOW_REQUESTS_TOTAL,
    NullShadowDispatcher,
    ShadowObserver,
    ShadowPipeline,
    in_shadow_sample,
    maybe_mirror_intent,
    shadow_active,
    shadow_capabilities,
    shadow_enabled,
    shadow_sample_pct,
)

_PROD = {"BANXE_ENV": "production", "INTENT_LAYER_SHADOW_ENABLED_PROD": "true"}


class _ExplodingDispatcher(AgentDispatchPort):
    """Fails the test loudly if the shadow ever tries to dispatch (= a live action)."""

    def dispatch(self, request: DispatchRequest) -> DispatchReceipt:  # pragma: no cover
        raise AssertionError(f"shadow dispatched {request.capability!r} — must never act")


# ── Gates: flag + production + sampling ─────────────────────────────────────────────


def test_shadow_inactive_when_flag_off_even_in_production():
    assert shadow_enabled({"BANXE_ENV": "production"}) is False
    assert shadow_active({"BANXE_ENV": "production"}) is False


def test_shadow_inactive_outside_production_even_when_flag_on():
    # A flag leaked to staging/dev/CI must not activate shadow anywhere but prod.
    for env_value in ("staging", "dev", "unknown", ""):
        env = {"BANXE_ENV": env_value, "INTENT_LAYER_SHADOW_ENABLED_PROD": "true"}
        assert shadow_active(env) is False


def test_shadow_active_only_in_production_with_flag_on():
    assert shadow_active(_PROD) is True


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(None, 1), ("", 1), ("0", 0), ("100", 100), ("250", 100), ("-5", 0), ("oops", 0)],
)
def test_shadow_sample_pct_clamps_and_fails_closed(raw, expected):
    env = {} if raw is None else {"INTENT_LAYER_SHADOW_SAMPLE_PCT": raw}
    assert shadow_sample_pct(env) == expected


def test_in_shadow_sample_is_deterministic_and_bounded():
    assert in_shadow_sample("any-id", 0) is False
    assert in_shadow_sample("any-id", 100) is True
    # Deterministic: same id → same decision every time.
    assert in_shadow_sample("corr-xyz", 50) == in_shadow_sample("corr-xyz", 50)


# ── shadow_capabilities: prod gate + high-risk subtraction ──────────────────────────


def test_shadow_capabilities_empty_outside_production():
    assert shadow_capabilities({"BANXE_ENV": "staging"}) == frozenset()
    assert shadow_capabilities({}) == frozenset()


def test_shadow_capabilities_defaults_to_staging_scope_in_production():
    # Same low-risk scope as the staging canary — never wider (FU-2 guardrail).
    assert shadow_capabilities(_PROD) == frozenset({"notifications", "referral"})


def test_shadow_capabilities_subtracts_high_risk_even_if_configured():
    env = {**_PROD, "INTENT_LAYER_SHADOW_CAPABILITIES": "Notifications,Payments,FX / Exchange"}
    # Payments + FX are mechanically dropped; only the low-risk surface remains.
    assert shadow_capabilities(env) == frozenset({"notifications"})


# ── NullShadowDispatcher: never acts ────────────────────────────────────────────────


def test_null_shadow_dispatcher_never_accepts():
    req = DispatchRequest(
        capability="Notifications", process_refs=(), resolved_intent=None, correlation_id="c1"
    )
    receipt = NullShadowDispatcher().dispatch(req)
    assert receipt.accepted is False
    assert receipt.agent == "(shadow)"


# ── ShadowPipeline.mirror ───────────────────────────────────────────────────────────


def _pipeline(metrics: InMemoryCanaryMetrics, dispatcher=None) -> ShadowPipeline:
    return ShadowPipeline(
        dispatcher=dispatcher if dispatcher is not None else NullShadowDispatcher(),
        observer=ShadowObserver(metrics, env="production"),
        env="production",
        capabilities=frozenset({"notifications", "referral"}),
    )


def test_mirror_low_risk_match_records_request_no_mismatch():
    metrics = InMemoryCanaryMetrics()
    comparison = _pipeline(metrics).mirror("notifications", "Notifications", "c-notif")
    assert comparison is not None
    assert comparison.shadow_disposition == "DISPATCHED"
    assert comparison.shadow_capability == "Notifications"
    assert comparison.mismatch is False
    assert metrics.counter_total(SHADOW_REQUESTS_TOTAL, mode="shadow", env="production") == 1
    assert metrics.counter_total(SHADOW_MISMATCH_TOTAL) == 0


def test_mirror_baseline_vs_shadow_mismatch_is_counted():
    # The Support surface has no canonical intent → IL resolves it to nothing
    # (governance event), which differs from the "Support" baseline = a mismatch.
    metrics = InMemoryCanaryMetrics()
    comparison = _pipeline(metrics).mirror("support ticket", "Support", "c-support")
    assert comparison is not None
    assert comparison.shadow_disposition == "GOVERNANCE_EVENT"
    assert comparison.shadow_capability is None
    assert comparison.mismatch is True
    assert metrics.counter_total(SHADOW_MISMATCH_TOTAL, mode="shadow") == 1


def test_mirror_high_risk_intent_is_held_and_never_dispatched():
    # "pay" → Payments (high-risk). It is outside the shadow allow-list, so the router
    # holds it BEFORE the dispatch boundary — the exploding dispatcher is never reached.
    metrics = InMemoryCanaryMetrics()
    pipeline = _pipeline(metrics, dispatcher=_ExplodingDispatcher())
    comparison = pipeline.mirror("pay", "Payments", "c-pay")
    assert comparison is not None
    assert comparison.shadow_disposition == "CANARY_HELD"
    assert comparison.shadow_capability == "Payments"
    # No error was recorded (held is a correct, expected non-action, not a failure).
    assert metrics.counter_total(SHADOW_ERRORS_TOTAL) == 0


def test_mirror_swallows_errors_and_never_raises():
    # A broken catalogue makes classification raise; mirror must swallow it, count an
    # error, and return None so the live caller is unaffected.
    metrics = InMemoryCanaryMetrics()
    pipeline = ShadowPipeline(
        catalog=object(),  # has no .lookup → AttributeError inside classify
        observer=ShadowObserver(metrics, env="production"),
        env="production",
        capabilities=frozenset({"notifications"}),
    )
    assert pipeline.mirror("notifications", "Notifications", "c-err") is None
    assert metrics.counter_total(SHADOW_ERRORS_TOTAL, mode="shadow") == 1


# ── maybe_mirror_intent hook ────────────────────────────────────────────────────────


def test_hook_is_noop_when_inactive(caplog):
    import logging

    with caplog.at_level(logging.INFO, logger="banxe.intent_layer.shadow"):
        assert maybe_mirror_intent("notifications", "Notifications", env={}) is None
    assert "intent_layer.shadow" not in caplog.text


def test_hook_mirrors_when_active_and_sampled():
    env = {**_PROD, "INTENT_LAYER_SHADOW_SAMPLE_PCT": "100"}
    comparison = maybe_mirror_intent("referral", "Referral / CRM", correlation_id="c-ref", env=env)
    assert comparison is not None
    assert comparison.shadow_capability == "Referral / CRM"
    assert comparison.mismatch is False


def test_hook_skips_unsampled_request():
    env = {**_PROD, "INTENT_LAYER_SHADOW_SAMPLE_PCT": "0"}
    assert maybe_mirror_intent("notifications", "Notifications", env=env) is None
