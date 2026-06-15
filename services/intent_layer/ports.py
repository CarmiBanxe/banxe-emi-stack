"""
services/intent_layer/ports.py — L1 Intent Layer injected ports (interfaces only)
IL-126-INTENT-LAYER-CLIENT-MASKS-2026-06-07 | banxe-emi-stack

L1 is CROSS-REPO: it dispatches to client-facing agents that live in BOTH
banxe-payment-core and banxe-emi-stack. To avoid a hard dependency on either agent
repo's internals, L1 talks to the outside world only through these Protocol ports.
Concrete wiring (the 9 masks, the S1 LLM gateway) is composition-root work, injected
at the seam — NOT imported here. This keeps the layer unit-testable without live infra.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from services.intent_layer.models import IntentDefinition, ProcessRef, ResolvedIntent

# ── LLM fallback port (S1 gateway seam) ──────────────────────────────────────────


@dataclass(frozen=True)
class LLMClassification:
    """A fuzzy match proposed by the LLM fallback. Always names an existing intent
    token from the catalog — the classifier re-validates it, the LLM never invents a
    process_ref (ADR-048 D3.3: no improvisation)."""

    matched_intent: str
    confidence: float


@runtime_checkable
class LLMClassifierPort(Protocol):
    """S1-gateway-backed fuzzy classifier. Only consulted when deterministic matching
    fails AND INTENT_LAYER_ENABLED is true. Returns None when it cannot confidently
    map the text to one of ``candidates`` (the catalog's intent definitions)."""

    def classify(
        self, intent_text: str, candidates: list[IntentDefinition]
    ) -> LLMClassification | None: ...


class NullLLMClassifier:
    """Default LLM port: always abstains. Lets the whole layer be exercised with zero
    live-LLM dependency — deterministic classification is fully testable without it."""

    def classify(
        self, intent_text: str, candidates: list[IntentDefinition]
    ) -> LLMClassification | None:
        return None


# ── Agent dispatch port (L1 → L2 seam) ───────────────────────────────────────────


@dataclass(frozen=True)
class DispatchRequest:
    """The structured hand-off L1 passes across the L1→L2 boundary (ADR-049 D2).

    Carries the resolved process_ref(s) so the L2 agent's §D2 chain has its process_ref
    gate already satisfied — the agent never re-resolves, it executes within its mask.
    """

    capability: str
    process_refs: tuple[ProcessRef, ...]
    resolved_intent: ResolvedIntent
    correlation_id: str

    @property
    def process_ref(self) -> ProcessRef:
        """Primary process_ref (first declared) — convenience for single-process masks."""
        return self.process_refs[0]


@dataclass(frozen=True)
class DispatchReceipt:
    """Acknowledgement returned by a client-facing agent on accepting the hand-off."""

    accepted: bool
    agent: str
    detail: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@runtime_checkable
class AgentDispatchPort(Protocol):
    """The injected handle to the 9 client-facing agents (in payment-core + emi-stack).
    Concrete implementations are wired at the composition root, keyed by capability —
    NOT imported into this layer."""

    def dispatch(self, request: DispatchRequest) -> DispatchReceipt: ...
