"""GAP-A — BestSolutionScorer: deterministic best-action selection (ADR-030 §R6).

Adapts ConfidenceScorer pattern (ADR-049 §D4):
  adj = base_score * root_cause_confidence - ambiguity * _AMBIGUITY_WEIGHT - risk_class_penalty

Lexicographic: L0 MANUAL_ONLY gate → L1 threshold → ESCALATE.
I-27: uncertain → ESCALATE. PII-free, clock-free (auditable).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from services.watchdog.decision_policy import (
    ACTION_CLASS_MAP,
    GUARDED_AUTO_THRESHOLD,
    SAFE_AUTO_THRESHOLD,
    ActionClass,
    ActionScore,
    ActionScorer,
    DefaultActionScorer,
    RepairAction,
)

# Mirrors ConfidenceScorer._AMBIGUITY_WEIGHT (ADR-049 §D4)
_AMBIGUITY_WEIGHT: float = 0.20

# Maps action class to risk penalty — mirrors _RISK_PENALTY in ConfidenceScorer
_RISK_CLASS_PENALTY: dict[ActionClass, float] = {
    ActionClass.SAFE: 0.0,
    ActionClass.GUARDED: 0.05,
    ActionClass.MANUAL_ONLY: 0.15,
}

# Unconditional ESCALATE when root_cause_confidence is too low to trust
_LOW_CONFIDENCE_THRESHOLD: float = 0.40


@dataclass(frozen=True)
class BestSolutionContext:
    """Input context for BestSolutionScorer — no PII, no clock values."""

    failure_reason: str
    root_cause_confidence: float  # 0.0–1.0 from diagnostic classifier
    restart_count: int = 0
    extra: dict = field(default_factory=dict)  # forwarded to DefaultActionScorer


@dataclass(frozen=True)
class BestSolutionCandidate:
    """One scored action with both base (ActionScore.score) and adjusted values."""

    action: RepairAction
    base_score: float  # from ActionScore.score formula
    adjusted_score: float  # post ADR-049 §D4 formula
    is_manual_only: bool


def _compute_ambiguity(sorted_base_scores: list[float]) -> float:
    """Compute competitive ambiguity from sorted automatable base scores.

    Ambiguity = 1 - normalised gap between top-1 and top-2.
    High ambiguity means the runner-up is close → less confident in choice.
    """
    if len(sorted_base_scores) < 2:
        return 0.0
    top = sorted_base_scores[0]
    second = sorted_base_scores[1]
    if top <= 0.0:
        return 1.0
    gap = (top - second) / top
    return round(max(0.0, 1.0 - gap), 4)


class BestSolutionScorer:
    """ADR-030 §R6: enumerate → score → satisfice → escalate.

    Protocol DI: inject a custom ActionScorer for tests; defaults to DefaultActionScorer.
    MANUAL_ONLY actions (incl. ESCALATE) are never auto-selected — enforced here.
    """

    def __init__(self, scorer: ActionScorer | None = None) -> None:
        self._scorer: ActionScorer = scorer or DefaultActionScorer()

    def score_candidates(self, ctx: BestSolutionContext) -> list[BestSolutionCandidate]:
        """Return all candidates sorted by adjusted_score descending."""
        raw: list[ActionScore] = self._scorer.score_actions(
            ctx.failure_reason, {"restart_count": ctx.restart_count, **ctx.extra}
        )

        # Phase 1: collect automatable base scores for ambiguity computation
        automatable_bases: list[float] = sorted(
            [
                round(a.score, 6)
                for a in raw
                if ACTION_CLASS_MAP.get(a.action, ActionClass.MANUAL_ONLY)
                != ActionClass.MANUAL_ONLY
            ],
            reverse=True,
        )
        ambiguity = _compute_ambiguity(automatable_bases)

        # Phase 2: apply adjusted score formula to every candidate
        result: list[BestSolutionCandidate] = []
        for raw_score in raw:
            action_class = ACTION_CLASS_MAP.get(raw_score.action, ActionClass.MANUAL_ONLY)
            is_manual_only = action_class == ActionClass.MANUAL_ONLY
            risk_penalty = _RISK_CLASS_PENALTY.get(action_class, 0.15)

            # ADR-049 §D4 adaptation: base * confidence - ambiguity_penalty - risk_penalty
            adj = (
                round(raw_score.score, 6) * ctx.root_cause_confidence
                - ambiguity * _AMBIGUITY_WEIGHT
                - risk_penalty
            )
            adj = round(max(0.0, min(1.0, adj)), 6)

            result.append(
                BestSolutionCandidate(
                    action=raw_score.action,
                    base_score=round(raw_score.score, 6),
                    adjusted_score=adj,
                    is_manual_only=is_manual_only,
                )
            )

        result.sort(key=lambda c: c.adjusted_score, reverse=True)
        return result

    def select(self, ctx: BestSolutionContext) -> RepairAction:
        """Select best automatable action, or ESCALATE.

        Escalation conditions (I-27 — any one triggers ESCALATE):
        - root_cause_confidence < _LOW_CONFIDENCE_THRESHOLD
        - no automatable candidates
        - best adjusted_score < autonomy-class threshold
        - best action is MANUAL_ONLY (belt-and-braces)
        """
        if ctx.root_cause_confidence < _LOW_CONFIDENCE_THRESHOLD:
            return RepairAction.ESCALATE

        candidates = self.score_candidates(ctx)
        automatable = [c for c in candidates if not c.is_manual_only]
        if not automatable:
            return RepairAction.ESCALATE

        best = automatable[0]
        action_class = ACTION_CLASS_MAP.get(best.action, ActionClass.MANUAL_ONLY)

        if action_class == ActionClass.SAFE and best.adjusted_score >= SAFE_AUTO_THRESHOLD:
            return best.action
        if action_class == ActionClass.GUARDED and best.adjusted_score >= GUARDED_AUTO_THRESHOLD:
            return best.action

        return RepairAction.ESCALATE
