"""
services/intent_layer/router.py — L1 IntentRouter
IL-126-INTENT-LAYER-CLIENT-MASKS-2026-06-07 | banxe-emi-stack

ADR-049 D1.4 hand-off + D2 chain. route(ResolvedIntent) → Disposition.

Ordered guards (ADR-049 D2 invariants):
  1. INTENT_LAYER_ENABLED false  → NOT_ENABLED, NO dispatch (safe pre-activation).
  2. UNRESOLVED intent           → GOVERNANCE_EVENT (HITL / process-gap), NO dispatch,
                                    never improvised (ADR-048 D3.3).
  3. CANARY GATE (FU-2 Phase 5)  → when a CanaryPolicy is injected, a resolved intent
                                    must clear the canary gate before dispatch:
                                      • high-risk capability  → GOVERNANCE_EVENT (manual
                                        flow); never auto-dispatched, even if allowlisted.
                                      • not in the allowlist   → NOT_ENABLED-shaped no-op
                                        (identical to dark-mode: no dispatch).
                                    With no policy injected, this guard is inert and the
                                    router behaves exactly as before (dispatch all).
  4. otherwise                   → select the client-facing mask by capability and
                                    dispatch via the injected AgentDispatchPort, passing
                                    the resolved process_ref(s) so the L2 agent's §D2
                                    chain has its process_ref gate already satisfied.

The router holds NO concrete agent imports — the 9 masks are reached only through the
injected AgentDispatchPort (cross-repo: payment-core + emi-stack).
"""

from __future__ import annotations

from services.intent_layer.canary import CanaryDecision, CanaryPolicy
from services.intent_layer.canary_metrics import CanaryObserver, NullCanaryObserver
from services.intent_layer.models import Disposition, DispositionKind, ResolvedIntent
from services.intent_layer.ports import AgentDispatchPort, DispatchRequest


class IntentRouter:
    """Dispatches a ResolvedIntent to its client-facing agent under the feature flag."""

    def __init__(
        self,
        dispatcher: AgentDispatchPort,
        *,
        enabled: bool = False,
        canary: CanaryPolicy | None = None,
        observer: CanaryObserver | None = None,
    ) -> None:
        self._dispatcher = dispatcher
        self._enabled = enabled
        self._canary = canary
        self._observer: CanaryObserver = observer or NullCanaryObserver()

    def route(self, resolved: ResolvedIntent) -> Disposition:
        if not self._enabled:
            return Disposition(
                kind=DispositionKind.NOT_ENABLED,
                correlation_id=resolved.correlation_id,
                reason="INTENT_LAYER_ENABLED is false — no dispatch (safe pre-activation)",
            )

        if not resolved.is_resolved:
            return Disposition(
                kind=DispositionKind.GOVERNANCE_EVENT,
                correlation_id=resolved.correlation_id,
                reason="intent resolved to no canonical process — HITL / process-gap (ADR-048 D3.3)",
            )

        gated = self._apply_canary(resolved)
        if gated is not None:
            return gated

        request = DispatchRequest(
            capability=resolved.capability,  # type: ignore[arg-type]  # resolved ⇒ non-None
            process_refs=resolved.process_refs,
            resolved_intent=resolved,
            correlation_id=resolved.correlation_id,
        )
        receipt = self._dispatcher.dispatch(request)
        return Disposition(
            kind=DispositionKind.DISPATCHED,
            correlation_id=resolved.correlation_id,
            capability=resolved.capability,
            process_refs=resolved.process_refs,
            receipt=receipt,
        )

    def _apply_canary(self, resolved: ResolvedIntent) -> Disposition | None:
        """Canary gate (guard 3). Returns a withholding Disposition when the policy
        denies dispatch, or None to let the dispatch proceed. Inert without a policy."""
        if self._canary is None:
            return None

        capability = resolved.capability or ""
        outcome = self._canary.decide(capability, resolved.matched_intent)
        self._observer.observe(
            decision=outcome.decision,
            capability=capability,
            correlation_id=resolved.correlation_id,
        )

        if outcome.decision is CanaryDecision.WITHHELD_HIGH_RISK:
            # Mechanistic high-risk guardrail: route to the human/manual flow, never
            # auto-dispatch — same response shape as a governance event.
            return Disposition(
                kind=DispositionKind.GOVERNANCE_EVENT,
                correlation_id=resolved.correlation_id,
                capability=resolved.capability,
                reason=outcome.reason,
            )
        if outcome.decision is CanaryDecision.WITHHELD_NOT_CANARY:
            # Outside the canary scope: degrade safely to dark-mode (no dispatch).
            return Disposition(
                kind=DispositionKind.NOT_ENABLED,
                correlation_id=resolved.correlation_id,
                capability=resolved.capability,
                reason=outcome.reason,
            )
        return None
