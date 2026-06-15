"""
services/intent_layer/classifier.py — L1 IntentClassifier
IL-126-INTENT-LAYER-CLIENT-MASKS-2026-06-07 | banxe-emi-stack

ADR-049 D1 capture+resolve. classify(intent_text) → ResolvedIntent.

Classification is DETERMINISTIC FIRST: exact/alias match against the S3 intent→process
map (already version-resolved by IntentCatalog), confidence 1.0 (AUTO band). Only when
deterministic matching fails AND INTENT_LAYER_ENABLED is true is the injected
LLMClassifierPort consulted — and it must name an EXISTING catalog intent, which the
classifier re-validates (the LLM never invents a process_ref). An intent that resolves
to no canonical process is UNRESOLVED → a governance event (ADR-048 D3.3 / ADR-049 D2),
never improvised.
"""

from __future__ import annotations

import uuid

from services.intent_layer.catalog import IntentCatalog
from services.intent_layer.models import (
    IntentDefinition,
    IntentStatus,
    MatchSource,
    ResolvedIntent,
)
from services.intent_layer.ports import LLMClassifierPort, NullLLMClassifier

_EXACT_CONFIDENCE = 1.0


class IntentClassifier:
    """Resolves free-form client intent text to a ResolvedIntent."""

    def __init__(
        self,
        catalog: IntentCatalog,
        *,
        enabled: bool = False,
        llm: LLMClassifierPort | None = None,
    ) -> None:
        self._catalog = catalog
        self._enabled = enabled
        self._llm: LLMClassifierPort = llm if llm is not None else NullLLMClassifier()

    def classify(self, intent_text: str, *, correlation_id: str | None = None) -> ResolvedIntent:
        """Capture+resolve one client intent. Always returns a ResolvedIntent; an
        unmatched intent yields status=UNRESOLVED (governance event), never an exception."""
        cid = correlation_id or uuid.uuid4().hex

        match = self._catalog.lookup(intent_text)
        if match is not None:
            source = MatchSource.EXACT if _is_exact(match, intent_text) else MatchSource.ALIAS
            return self._resolved(intent_text, cid, match, _EXACT_CONFIDENCE, source)

        llm_match = self._fuzzy(intent_text)
        if llm_match is not None:
            definition, confidence = llm_match
            return self._resolved(intent_text, cid, definition, confidence, MatchSource.LLM)

        return ResolvedIntent(
            raw_text=intent_text,
            correlation_id=cid,
            status=IntentStatus.UNRESOLVED,
            confidence=0.0,
            match_source=MatchSource.NONE,
        )

    # ── internals ────────────────────────────────────────────────────────────────

    def _fuzzy(self, intent_text: str) -> tuple[IntentDefinition, float] | None:
        """Gated LLM fallback: only when enabled. Re-validates the proposed intent
        against the catalog so a hallucinated token cannot resolve to a process_ref."""
        if not self._enabled:
            return None
        proposal = self._llm.classify(intent_text, self._catalog.definitions)
        if proposal is None:
            return None
        definition = self._catalog.by_intent(proposal.matched_intent)
        if definition is None:
            return None
        return definition, proposal.confidence

    @staticmethod
    def _resolved(
        text: str,
        cid: str,
        definition: IntentDefinition,
        confidence: float,
        source: MatchSource,
    ) -> ResolvedIntent:
        return ResolvedIntent(
            raw_text=text,
            correlation_id=cid,
            status=IntentStatus.RESOLVED,
            confidence=confidence,
            match_source=source,
            matched_intent=definition.intent,
            capability=definition.capability,
            process_refs=definition.process_refs,
        )


def _is_exact(definition: IntentDefinition, text: str) -> bool:
    return " ".join(text.lower().split()) == " ".join(definition.intent.lower().split())
