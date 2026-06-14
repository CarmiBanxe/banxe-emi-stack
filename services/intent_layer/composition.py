"""
services/intent_layer/composition.py — L1→L2 composition root (S8).

This is the COMPOSITION ROOT the ADR-049 ports were designed for. The pure layer
(``classifier``/``router``/``ports``/``models``) never imports it, so the
dependency is one-way (composition → layer + agents + producers) and the layer
stays unit-testable in isolation; this module MAY import the L2 agents and the
S5.2 producers to build the concrete seam implementations.

It provides the two pieces that turn the L1 seam into a working chat→L1→L2→port→
lineage flow:

  • :class:`InMemoryDecisionRecorder` — a :class:`DecisionRecorder` (ADR-046 sink)
    that keeps records in memory keyed by ``correlation_id``. It backs the GET
    lineage endpoint and the in-memory acceptance proof; the ClickHouse sink
    (ADR-002, S4) is the operator runtime step, injected in its place when live.

  • :class:`CapabilityDispatcher` — an :class:`AgentDispatchPort` that runs the
    S5.2 :class:`ProducerBundle` (compliance/confidence/cost — REPLACING the
    agents' default-PASS) and dispatches the resolved intent to the in-process L2
    mask registered for its capability, capturing the emitted
    :class:`AgentDecisionRecord`. A capability with no in-process mask (e.g.
    Payments/FX/Wallet — owned by banxe-payment-core) returns an *unrouted*
    receipt; the cross-repo dispatch is the operator runtime step.

R-SEC: only opaque handles cross the seam — :class:`ComplianceCheckRequest`
carries an opaque ``subject_ref`` derived from the correlation id, never PII.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor

from services.agents._lineage import AgentDecisionRecord, AgentOutcome, DecisionRecorder
from services.intent_layer.canary import is_high_risk_capability, normalize_capability
from services.intent_layer.ports import (
    AgentDispatchPort,
    DispatchReceipt,
    DispatchRequest,
)
from services.producers.bundle import ProducerBundle, ProducerOutputs
from services.producers.confidence_scorer import ScoringSignals
from services.producers.ports import ComplianceCheckRequest

# A capability handler builds the target mask's typed intent from the resolved
# envelope + the produced inputs, invokes the mask's §D2 chain, and returns the
# resulting :class:`AgentOutcome` (which always carries an emitted record). It is
# async because every L2 mask action is async; the dispatcher bridges to sync.
CapabilityHandler = Callable[
    [DispatchRequest, ProducerOutputs, DecisionRecorder], Awaitable[AgentOutcome]
]

# Tokens estimated per L1-dispatched invocation for the cost producer (static
# default; live S1-gateway accounting overrides it via CostSourcePort when wired).
_DEFAULT_EST_TOKENS = 256


# ── Lineage sink ─────────────────────────────────────────────────────────────


class InMemoryDecisionRecorder(DecisionRecorder):
    """In-memory :class:`DecisionRecorder` — the safe default sink (ADR-046).

    Keyed by ``correlation_id`` so the GET lineage endpoint can resolve a decision
    by the same id the chat surface holds. The durable ClickHouse sink (S4) is
    injected in its place when live; the agents depend only on the interface.
    """

    def __init__(self) -> None:
        self._by_correlation: dict[str, AgentDecisionRecord] = {}
        self._by_record: dict[str, AgentDecisionRecord] = {}
        self._all: list[AgentDecisionRecord] = []

    async def record(self, record: AgentDecisionRecord) -> None:
        self._by_correlation[record.correlation_id] = record
        self._by_record[record.record_id] = record
        self._all.append(record)

    def get_by_correlation(self, correlation_id: str) -> AgentDecisionRecord | None:
        """Latest record emitted for a correlation id; None when none was recorded."""
        return self._by_correlation.get(correlation_id)

    @property
    def records(self) -> list[AgentDecisionRecord]:
        """All records in emission order (diagnostics / tests)."""
        return list(self._all)


# ── Producer inputs ──────────────────────────────────────────────────────────


def _subject_ref(correlation_id: str) -> str:
    """Opaque, derived subject handle for the compliance check — NEVER PII.

    The real screening identity is resolved L3-side inside an adapter behind
    :class:`SanctionsIdentityPort`; nothing here threads a name/account number.
    """
    return f"subj-{correlation_id}"


def default_check_request(request: DispatchRequest) -> ComplianceCheckRequest:
    """Build the non-PII compliance-check input for a dispatched intent.

    The live router uses this benign default (no sanctions/PEP flags); a wired
    composition (or a test) injects a builder that derives the risk flags from an
    upstream structured signal — never by regex-parsing the free-form text.
    """
    resolved = request.resolved_intent
    return ComplianceCheckRequest(
        action=resolved.matched_intent or request.capability,
        correlation_id=request.correlation_id,
        subject_ref=_subject_ref(request.correlation_id),
    )


# ── Async→sync bridge ────────────────────────────────────────────────────────


def _run_sync(coro: Awaitable[AgentOutcome]) -> AgentOutcome:
    """Drive an async mask action to completion from the sync dispatch boundary.

    ``AgentDispatchPort.dispatch`` is synchronous (ADR-049 seam); the masks are
    async. When called outside an event loop (sync FastAPI route in the
    threadpool, or a sync test) we use ``asyncio.run``; if a loop is already
    running we hand the coroutine to a fresh loop on a worker thread so we never
    nest event loops.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)  # no running loop — safe
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(coro)).result()


# ── L1 → L2 dispatch ─────────────────────────────────────────────────────────


def _cap_key(capability: str) -> str:
    """Normalise a catalogue capability label to a stable registry key.

    Thin alias for :func:`services.intent_layer.canary.normalize_capability` — the
    single source of truth for the key shape, so handler registration here and the
    canary allow-list gating in the router never diverge.
    """
    return normalize_capability(capability)


class CapabilityDispatcher(AgentDispatchPort):
    """Routes a resolved intent to its in-process L2 mask, populating the agent
    inputs from the S5.2 producers and capturing the emitted lineage record."""

    def __init__(
        self,
        *,
        handlers: dict[str, CapabilityHandler],
        producers: ProducerBundle,
        recorder: DecisionRecorder,
        check_request_builder: Callable[[DispatchRequest], ComplianceCheckRequest] | None = None,
        est_tokens: int = _DEFAULT_EST_TOKENS,
        risk_class: str = "STANDARD",
        enforce_high_risk_denylist: bool = False,
    ) -> None:
        self._handlers = {_cap_key(k): v for k, v in handlers.items()}
        self._producers = producers
        self._recorder = recorder
        self._build_check = check_request_builder or default_check_request
        self._est_tokens = est_tokens
        self._risk_class = risk_class
        # FU-2 Phase 7 canary policy: when set, a money/FX/wallet/card/KYC/SAR/sanctions
        # capability is mechanically refused at this boundary (defense-in-depth backstop
        # behind the router's allow-list). Off by default so the generic L1→L2 dispatch
        # mechanism stays policy-free; the staging canary composition turns it ON.
        self._enforce_high_risk_denylist = enforce_high_risk_denylist

    def dispatch(self, request: DispatchRequest) -> DispatchReceipt:
        # Hard guardrail (FU-2 Phase 7, defense-in-depth): a money/FX/wallet/card/KYC/
        # SAR/sanctions capability is mechanically refused at the dispatch boundary —
        # BEFORE any producer runs or handler is consulted — even if it was mistakenly
        # added to the canary allow-list or a handler was registered for it. The
        # router's allow-list is the first gate; this is the fail-closed backstop.
        if self._enforce_high_risk_denylist and is_high_risk_capability(request.capability):
            return DispatchReceipt(
                accepted=False,
                agent="(blocked)",
                detail=(
                    f"high-risk capability {request.capability!r} is mechanically blocked "
                    "from canary dispatch (FU-2 Phase 7 denylist)"
                ),
                metadata={
                    "blocked": "high_risk",
                    "capability_key": normalize_capability(request.capability),
                },
            )
        outputs = self._produce(request)
        handler = self._handlers.get(_cap_key(request.capability))
        if handler is None:
            return DispatchReceipt(
                accepted=False,
                agent="(unrouted)",
                detail=(
                    f"no in-process L2 mask for capability {request.capability!r} "
                    "(cross-repo masks are the operator runtime step)"
                ),
                metadata={"capability_key": _cap_key(request.capability)},
            )
        outcome = _run_sync(handler(request, outputs, self._recorder))
        return self._receipt(outcome)

    def _produce(self, request: DispatchRequest) -> ProducerOutputs:
        """Run the three producers — the real compliance/confidence/cost inputs
        that REPLACE the agents' default-PASS (S5.2 audit gap #6)."""
        signals = ScoringSignals.from_resolved_intent(
            request.resolved_intent, risk_class=self._risk_class
        )
        return self._producers.produce(
            check_request=self._build_check(request),
            signals=signals,
            est_tokens=self._est_tokens,
        )

    @staticmethod
    def _receipt(outcome: AgentOutcome) -> DispatchReceipt:
        record = outcome.record
        return DispatchReceipt(
            accepted=True,  # the mask accepted the hand-off and emitted a record
            agent=record.agent_id,
            detail=record.action_taken,
            metadata={
                "record_id": record.record_id,
                "correlation_id": record.correlation_id,
                "compliance_result": str(record.compliance_result),
                "decision": str(outcome.decision),
                "executed": str(outcome.executed).lower(),
            },
        )


__all__ = [
    "CapabilityDispatcher",
    "CapabilityHandler",
    "InMemoryDecisionRecorder",
    "default_check_request",
]
