"""
services/intent_layer/router.py — L1 IntentRouter
IL-126-INTENT-LAYER-CLIENT-MASKS-2026-06-07 | banxe-emi-stack

ADR-049 D1.4 hand-off + D2 chain. route(ResolvedIntent) → Disposition.

Ordered guards (ADR-049 D2 invariants):
  1. INTENT_LAYER_ENABLED false  → NOT_ENABLED, NO dispatch (safe pre-activation).
  2. UNRESOLVED intent           → GOVERNANCE_EVENT (HITL / process-gap), NO dispatch,
                                    never improvised (ADR-048 D3.3).
  3. capability outside the      → CANARY_HELD, NO dispatch (FU-2 Phase 7 scope guard).
     canary allow-list             The optional ``canary_capabilities`` allow-list bounds
                                    which resolved capabilities the canary may dispatch in
                                    staging; ``None`` (the pure-seam default) imposes no
                                    bound. The composition root passes the env-bound,
                                    high-risk-subtracted set from ``canary.py``.
  4. otherwise                   → select the client-facing mask by capability and
                                    dispatch via the injected AgentDispatchPort, passing
                                    the resolved process_ref(s) so the L2 agent's §D2
                                    chain has its process_ref gate already satisfied.

The router holds NO concrete agent imports — the 9 masks are reached only through the
injected AgentDispatchPort (cross-repo: payment-core + emi-stack).
"""

from __future__ import annotations

from services.intent_layer.canary import normalize_capability
from services.intent_layer.models import Disposition, DispositionKind, ResolvedIntent
from services.intent_layer.ports import AgentDispatchPort, DispatchRequest


class IntentRouter:
    """Dispatches a ResolvedIntent to its client-facing agent under the feature flag.

    ``canary_capabilities`` is the optional staging canary scope (normalised capability
    keys, e.g. ``{"notifications", "referral"}``). ``None`` imposes no bound — the pure
    seam dispatches any resolved capability; the composition root passes the env-bound,
    high-risk-subtracted set (``canary.canary_capabilities``) so a resolved-but-out-of-
    scope intent is held dark instead of dispatched (FU-2 Phase 7)."""

    def __init__(
        self,
        dispatcher: AgentDispatchPort,
        *,
        enabled: bool = False,
        canary_capabilities: frozenset[str] | None = None,
    ) -> None:
        self._dispatcher = dispatcher
        self._enabled = enabled
        self._canary_capabilities = canary_capabilities

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

        if self._canary_capabilities is not None and (
            normalize_capability(resolved.capability or "") not in self._canary_capabilities
        ):
            return Disposition(
                kind=DispositionKind.CANARY_HELD,
                correlation_id=resolved.correlation_id,
                capability=resolved.capability,
                process_refs=resolved.process_refs,
                reason=(
                    f"capability {resolved.capability!r} is outside the staging canary "
                    "allow-list — held dark, no dispatch (FU-2 Phase 7)"
                ),
            )

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
