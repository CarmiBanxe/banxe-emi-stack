"""
services/producers/confidence_scorer.py — ConfidenceScorer (S5.2, ADR-049 §D4).

Produces the ``confidence_score`` [0,1] the L2 agents accept, from DETERMINISTIC
signals — no LLM, no I/O, no clock — so the same signals always yield the same
score (auditable). Signals:
  • match_source  — how L1 resolved the intent (EXACT/ALIAS high, LLM lower, NONE 0)
  • resolved      — an UNRESOLVED intent scores 0 (governance event, never AUTO)
  • ambiguity     — [0,1] competing-candidate pressure, subtracts confidence
  • risk_class    — STANDARD/ELEVATED/HIGH, higher risk shaves confidence

The score maps onto the existing ADR-049 §D4 :class:`ConfidenceBand` thresholds
(>0.90 AUTO, 0.70–0.90 REVIEW, <0.70 BLOCK) — NO new scale is introduced.
"""

from __future__ import annotations

from dataclasses import dataclass

from services.intent_layer.models import ConfidenceBand, MatchSource

# Deterministic base confidence per match source (auditable constants).
_BASE: dict[MatchSource, float] = {
    MatchSource.EXACT: 1.0,
    MatchSource.ALIAS: 0.95,
    MatchSource.LLM: 0.75,
    MatchSource.NONE: 0.0,
}

# Risk-class confidence penalties (higher risk → lower autonomy).
_RISK_PENALTY: dict[str, float] = {
    "STANDARD": 0.0,
    "ELEVATED": 0.05,
    "HIGH": 0.15,
}

_AMBIGUITY_WEIGHT = 0.20


@dataclass(frozen=True)
class ScoringSignals:
    """Deterministic inputs to the confidence score (no PII, no clock)."""

    match_source: MatchSource
    resolved: bool = True
    ambiguity: float = 0.0  # [0,1]
    risk_class: str = "STANDARD"  # STANDARD | ELEVATED | HIGH

    @classmethod
    def from_resolved_intent(
        cls, resolved_intent: object, *, ambiguity: float = 0.0, risk_class: str = "STANDARD"
    ) -> ScoringSignals:
        """Build signals from an L1 ``ResolvedIntent`` (duck-typed: reads
        ``match_source`` + ``is_resolved``) plus caller-supplied risk context."""
        return cls(
            match_source=resolved_intent.match_source,  # type: ignore[attr-defined]
            resolved=bool(resolved_intent.is_resolved),  # type: ignore[attr-defined]
            ambiguity=ambiguity,
            risk_class=risk_class,
        )


class ConfidenceScorer:
    """Deterministic producer of ``confidence_score`` ∈ [0,1]."""

    def score(self, signals: ScoringSignals) -> float:
        """Return the confidence score for the given signals (clamped to [0,1])."""
        if not signals.resolved or signals.match_source is MatchSource.NONE:
            return 0.0
        base = _BASE[signals.match_source]
        ambiguity = min(max(signals.ambiguity, 0.0), 1.0)
        penalty = _RISK_PENALTY.get(signals.risk_class.upper(), 0.0)
        raw = base - (ambiguity * _AMBIGUITY_WEIGHT) - penalty
        return round(min(max(raw, 0.0), 1.0), 4)

    def band(self, signals: ScoringSignals) -> ConfidenceBand:
        """ADR-049 §D4 band for the produced score."""
        return ConfidenceBand.of(self.score(signals))


__all__ = ["ConfidenceScorer", "ScoringSignals"]
