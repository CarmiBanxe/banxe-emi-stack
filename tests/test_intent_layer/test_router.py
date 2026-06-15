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


# ── FU-2 Phase 7: canary allow-list scope guard ──────────────────────────────────


def test_no_allowlist_dispatches_any_resolved_capability(catalog, spy_dispatcher):
    # The pure seam default (canary_capabilities=None) imposes no scope bound.
    router = IntentRouter(spy_dispatcher, enabled=True, canary_capabilities=None)
    assert router.route(_resolve(catalog, "pay")).kind is DispositionKind.DISPATCHED


def test_capability_in_allowlist_dispatches(catalog, spy_dispatcher):
    router = IntentRouter(
        spy_dispatcher, enabled=True, canary_capabilities=frozenset({"notifications", "referral"})
    )
    disposition = router.route(_resolve(catalog, "get-notified"))
    assert disposition.kind is DispositionKind.DISPATCHED
    assert disposition.capability == "Notifications"
    assert len(spy_dispatcher.calls) == 1


def test_capability_outside_allowlist_is_held(catalog, spy_dispatcher):
    # Resolved, but not in the canary scope → CANARY_HELD, never dispatched.
    router = IntentRouter(
        spy_dispatcher, enabled=True, canary_capabilities=frozenset({"notifications"})
    )
    disposition = router.route(_resolve(catalog, "refer-a-friend"))
    assert disposition.kind is DispositionKind.CANARY_HELD
    assert disposition.capability == "Referral / CRM"
    assert spy_dispatcher.calls == []  # held dark — no dispatch


def test_empty_allowlist_holds_everything(catalog, spy_dispatcher):
    # The non-staging effective allow-list is empty → every resolved intent is held.
    router = IntentRouter(spy_dispatcher, enabled=True, canary_capabilities=frozenset())
    for text in ("get-notified", "refer-a-friend", "pay"):
        assert router.route(_resolve(catalog, text)).kind is DispositionKind.CANARY_HELD
    assert spy_dispatcher.calls == []


def test_allowlist_does_not_override_disabled_gate(catalog, spy_dispatcher):
    # Even an allow-listed capability stays NOT_ENABLED when the flag is off (outermost guard).
    router = IntentRouter(
        spy_dispatcher, enabled=False, canary_capabilities=frozenset({"notifications"})
    )
    assert router.route(_resolve(catalog, "get-notified")).kind is DispositionKind.NOT_ENABLED
    assert spy_dispatcher.calls == []
