"""
tests/test_intent_layer/test_router.py — IntentRouter: gating, governance, dispatch
IL-126-INTENT-LAYER-CLIENT-MASKS-2026-06-07 | banxe-emi-stack
"""

from __future__ import annotations

from services.intent_layer.classifier import IntentClassifier
from services.intent_layer.models import (
    DispositionKind,
    IntentStatus,
    MatchSource,
    ProcessRef,
    ResolvedIntent,
)
from services.intent_layer.router import IntentRouter


def _resolve(catalog, text, *, enabled=True):
    return IntentClassifier(catalog, enabled=enabled).classify(text)


def test_disabled_router_does_not_dispatch(catalog, spy_dispatcher):
    router = IntentRouter(spy_dispatcher, enabled=False)
    disposition = router.route(_resolve(catalog, "pay"))
    assert disposition.kind is DispositionKind.NOT_ENABLED
    assert spy_dispatcher.calls == []  # no dispatch pre-activation


def test_unresolved_intent_routes_to_governance_event(catalog, spy_dispatcher):
    router = IntentRouter(spy_dispatcher, enabled=True)
    unresolved = _resolve(catalog, "teleport my cat")
    assert unresolved.status is IntentStatus.UNRESOLVED
    disposition = router.route(unresolved)
    assert disposition.kind is DispositionKind.GOVERNANCE_EVENT
    assert spy_dispatcher.calls == []  # never improvised into a dispatch


def test_resolved_intent_dispatches_with_process_ref(catalog, spy_dispatcher):
    router = IntentRouter(spy_dispatcher, enabled=True)
    resolved = _resolve(catalog, "exchange")
    disposition = router.route(resolved)

    assert disposition.kind is DispositionKind.DISPATCHED
    assert disposition.capability == "FX / Exchange"
    assert len(spy_dispatcher.calls) == 1
    request = spy_dispatcher.calls[0]
    # the L2 agent's §D2 process_ref gate is satisfied by the hand-off payload
    assert request.process_refs == (ProcessRef("fx-exchange", "1.0.0"),)
    assert request.process_ref == ProcessRef("fx-exchange", "1.0.0")
    assert request.capability == "FX / Exchange"
    assert request.correlation_id == resolved.correlation_id
    assert disposition.receipt.accepted is True
    assert disposition.receipt.agent == "agent:FX / Exchange"


def test_correlation_id_threads_through_disposition(catalog, spy_dispatcher):
    router = IntentRouter(spy_dispatcher, enabled=True)
    resolved = _resolve(catalog, "pay")
    disposition = router.route(resolved)
    assert disposition.correlation_id == resolved.correlation_id
    assert spy_dispatcher.calls[0].resolved_intent is resolved


def test_disabled_router_short_circuits_before_governance_check(catalog, spy_dispatcher):
    # Even an UNRESOLVED intent yields NOT_ENABLED (flag is the outermost guard).
    router = IntentRouter(spy_dispatcher, enabled=False)
    unresolved = ResolvedIntent(
        raw_text="x",
        correlation_id="c1",
        status=IntentStatus.UNRESOLVED,
        confidence=0.0,
        match_source=MatchSource.NONE,
    )
    assert router.route(unresolved).kind is DispositionKind.NOT_ENABLED


def test_dispatch_receipt_can_signal_rejection(catalog):
    from .conftest import SpyDispatcher

    rejecting = SpyDispatcher(accepted=False)
    router = IntentRouter(rejecting, enabled=True)
    disposition = router.route(_resolve(catalog, "pay"))
    assert disposition.kind is DispositionKind.DISPATCHED
    assert disposition.receipt.accepted is False
