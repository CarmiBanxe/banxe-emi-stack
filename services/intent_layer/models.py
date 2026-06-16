"""
services/intent_layer/models.py — L1 Intent Layer domain types
IL-126-INTENT-LAYER-CLIENT-MASKS-2026-06-07 | banxe-emi-stack

ADR-049 L1 Intent Layer (the CLIENT intent surface). NOT ADR-021 agent_routing —
that is the internal compliance/AML/KYC task-router to tier workers. This module is
the client-facing L1→L2 seam: classify a free-form client intent, resolve it to a
canonical ``process_ref = {process_id, version}`` (ADR-048 intent→process contract),
select the client-facing mask, and hand off to the L2 agent.

These are pure data types — no I/O, no LLM, no port wiring. They are the envelope the
classifier produces and the router consumes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

# ── Enumerations ────────────────────────────────────────────────────────────────


class IntentStatus(str, Enum):
    """Outcome of classifying a client intent against the intent→process map."""

    RESOLVED = "RESOLVED"  # matched an intent that resolves to ≥1 process_ref
    UNRESOLVED = "UNRESOLVED"  # no canonical process — ADR-048 D3.3 governance event


class ConfidenceBand(str, Enum):
    """ADR-049 D4 HITL bands — reused verbatim, NO new threshold scale introduced."""

    AUTO = "AUTO"  # confidence > 0.90
    REVIEW = "REVIEW"  # 0.70 ≤ confidence ≤ 0.90
    BLOCK = "BLOCK"  # confidence < 0.70

    @classmethod
    def of(cls, confidence: float) -> ConfidenceBand:
        """Map a confidence score onto the ADR-049 D4 band."""
        if confidence > 0.90:
            return cls.AUTO
        if confidence >= 0.70:
            return cls.REVIEW
        return cls.BLOCK


class MatchSource(str, Enum):
    """How the classifier arrived at a match — determinism is auditable per decision."""

    EXACT = "EXACT"  # canonical intent token matched
    ALIAS = "ALIAS"  # one of the intent's aliases matched
    LLM = "LLM"  # fuzzy LLM fallback (gated behind INTENT_LAYER_ENABLED + S1 gateway)
    NONE = "NONE"  # no match — UNRESOLVED


class DispositionKind(str, Enum):
    """What the router did with a ResolvedIntent."""

    DISPATCHED = "DISPATCHED"  # handed off to the L2 client-facing agent
    NOT_ENABLED = "NOT_ENABLED"  # INTENT_LAYER_ENABLED is false — safe pre-activation no-op
    GOVERNANCE_EVENT = "GOVERNANCE_EVENT"  # UNRESOLVED intent → HITL / process-gap backlog
    CANARY_HELD = "CANARY_HELD"  # resolved, but the capability is outside the staging
    #                              canary allow-list — held dark, NO dispatch (FU-2 Phase 7)


# ── Value objects ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ProcessRef:
    """ADR-048 resolvable handle: the {process_id, version} an intent resolves to.

    Conforms to banxe-architecture/schemas/process_ref.schema.json — a non-sensitive
    identifier pair that MUST NOT embed secrets or PII.
    """

    process_id: str
    version: str

    def __post_init__(self) -> None:
        if not self.process_id:
            raise ValueError("process_id must not be empty")
        if not self.version:
            raise ValueError("version must not be empty")

    def as_dict(self) -> dict[str, str]:
        return {"process_id": self.process_id, "version": self.version}


@dataclass(frozen=True)
class IntentDefinition:
    """One row of the S3 intent→process map (intent-process-map.yaml).

    process_refs are pre-resolved against processes-registry.json at catalog-load time,
    so an IntentDefinition always carries fully-versioned refs (never bare process_ids).
    """

    intent: str
    aliases: tuple[str, ...]
    capability: str
    process_refs: tuple[ProcessRef, ...]


# ── Classifier / router outputs ─────────────────────────────────────────────────


@dataclass(frozen=True)
class ResolvedIntent:
    """Structured, auditable request emitted by L1 capture+resolve (ADR-049 D1.4).

    This is the object that crosses the L1→L2 boundary. For an UNRESOLVED intent the
    process_refs tuple is empty and status is UNRESOLVED (governance event).
    """

    raw_text: str
    correlation_id: str
    status: IntentStatus
    confidence: float
    match_source: MatchSource
    matched_intent: str | None = None
    capability: str | None = None
    process_refs: tuple[ProcessRef, ...] = field(default_factory=tuple)

    @property
    def band(self) -> ConfidenceBand:
        """ADR-049 D4 confidence band for this resolution."""
        return ConfidenceBand.of(self.confidence)

    @property
    def is_resolved(self) -> bool:
        return self.status is IntentStatus.RESOLVED


@dataclass(frozen=True)
class Disposition:
    """Result of routing a ResolvedIntent — what L1 did and why."""

    kind: DispositionKind
    correlation_id: str
    capability: str | None = None
    process_refs: tuple[ProcessRef, ...] = field(default_factory=tuple)
    receipt: object | None = None  # AgentDispatchPort receipt, when DISPATCHED
    reason: str | None = None
