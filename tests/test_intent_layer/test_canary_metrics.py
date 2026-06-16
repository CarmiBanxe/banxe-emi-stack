"""
tests/test_intent_layer/test_canary_metrics.py — canary observability hooks.
"""

from __future__ import annotations

from services.intent_layer.canary import CanaryDecision
from services.intent_layer.canary_metrics import (
    CounterCanaryObserver,
    FanOutCanaryObserver,
    NullCanaryObserver,
)


def test_null_observer_is_noop():
    obs = NullCanaryObserver()
    obs.observe(decision=CanaryDecision.DISPATCH, capability="Notifications", correlation_id="c1")
    obs.observe_error(capability="Notifications", correlation_id="c1")  # no exception


def test_counter_tallies_decisions_and_snapshot():
    obs = CounterCanaryObserver()
    obs.observe(decision=CanaryDecision.DISPATCH, capability="Notifications", correlation_id="a")
    obs.observe(
        decision=CanaryDecision.WITHHELD_HIGH_RISK, capability="Payments", correlation_id="b"
    )
    obs.observe(
        decision=CanaryDecision.WITHHELD_NOT_CANARY, capability="Statements", correlation_id="c"
    )
    obs.observe_error(capability="Notifications", correlation_id="a")

    assert obs.total == 3
    assert obs.dispatched == 1
    assert obs.withheld == 2
    snap = obs.snapshot()
    assert snap == {
        "canary_intents_total": 3,
        "canary_dispatched": 1,
        "canary_withheld_not_canary": 1,
        "canary_withheld_high_risk": 1,
        "canary_errors": 1,
    }


def test_fanout_forwards_to_all_observers():
    a, b = CounterCanaryObserver(), CounterCanaryObserver()
    fan = FanOutCanaryObserver((a, b))
    fan.observe(decision=CanaryDecision.DISPATCH, capability="Notifications", correlation_id="x")
    fan.observe_error(capability="Notifications", correlation_id="x")
    assert a.dispatched == b.dispatched == 1
    assert a.errors == b.errors == 1
