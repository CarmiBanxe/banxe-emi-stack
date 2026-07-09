"""Tests for BestSolutionScorer (GAP-A).

Covers: clear-leader selection, low-confidence gate, high-ambiguity escalation,
MANUAL_ONLY boundary, GUARDED tier, score_candidates ordering.
"""

from __future__ import annotations

from services.watchdog.best_solution import (
    BestSolutionContext,
    BestSolutionScorer,
    _compute_ambiguity,
)
from services.watchdog.decision_policy import (
    ActionScore,
    RepairAction,
)

# ── stub scorers ──────────────────────────────────────────────────────────────


class _TwoCloseGUARDEDScorer:
    """Two GUARDED actions with nearly identical base scores → high ambiguity."""

    def score_actions(self, failure_reason: str, context: dict) -> list[ActionScore]:
        return [
            ActionScore(
                action=RepairAction.RESTART_OLLAMA,
                reversibility=0.95,
                blast_radius=0.15,
                confidence=0.799,
                time_to_recovery_s=45.0,
            ),
            ActionScore(
                action=RepairAction.RECREATE_CONTAINER,
                reversibility=0.800,
                blast_radius=0.145,
                confidence=0.801,
                time_to_recovery_s=20.0,
            ),
            ActionScore(
                action=RepairAction.ESCALATE,
                reversibility=0.0,
                blast_radius=1.0,
                confidence=0.0,
                time_to_recovery_s=3600.0,
            ),
        ]


# ── _compute_ambiguity unit tests ─────────────────────────────────────────────


def test_compute_ambiguity_empty_returns_zero() -> None:
    assert _compute_ambiguity([]) == 0.0


def test_compute_ambiguity_single_candidate_returns_zero() -> None:
    assert _compute_ambiguity([0.80]) == 0.0


def test_compute_ambiguity_identical_scores_returns_one() -> None:
    result = _compute_ambiguity([0.70, 0.70])
    assert result == 1.0


def test_compute_ambiguity_clear_leader_low_value() -> None:
    # top=0.80, second=0.10: gap=0.875 → ambiguity=0.125
    result = _compute_ambiguity([0.80, 0.10])
    assert result < 0.20


def test_compute_ambiguity_very_close_scores_high_value() -> None:
    # top=0.700, second=0.699: gap≈0.00143 → ambiguity≈0.9986
    result = _compute_ambiguity([0.700, 0.699])
    assert result > 0.99


def test_compute_ambiguity_zero_top_returns_one() -> None:
    result = _compute_ambiguity([0.0, 0.0])
    assert result == 1.0


# ── low confidence gate ───────────────────────────────────────────────────────


def test_low_confidence_escalates_immediately() -> None:
    scorer = BestSolutionScorer()
    ctx = BestSolutionContext(
        failure_reason="OLLAMA_PROCESS_DEAD",
        root_cause_confidence=0.35,  # below _LOW_CONFIDENCE_THRESHOLD=0.40
    )
    assert scorer.select(ctx) == RepairAction.ESCALATE


def test_confidence_just_below_threshold_escalates() -> None:
    scorer = BestSolutionScorer()
    ctx = BestSolutionContext(
        failure_reason="OLLAMA_PROCESS_DEAD",
        root_cause_confidence=0.399,
    )
    assert scorer.select(ctx) == RepairAction.ESCALATE


# ── SAFE tier ─────────────────────────────────────────────────────────────────


def test_safe_warm_model_selected_with_high_confidence() -> None:
    scorer = BestSolutionScorer()
    # WARM_MODEL base ≈ 0.8075; adj = 0.8075*0.90 ≈ 0.727 > SAFE_AUTO_THRESHOLD=0.60
    ctx = BestSolutionContext(
        failure_reason="COLD_STRIKE",
        root_cause_confidence=0.90,
    )
    assert scorer.select(ctx) == RepairAction.WARM_MODEL


def test_safe_score_below_threshold_escalates() -> None:
    scorer = BestSolutionScorer()
    # rc_conf=0.70 → WARM_MODEL adj ≈ 0.8075*0.70 ≈ 0.565 < 0.60
    ctx = BestSolutionContext(
        failure_reason="COLD_STRIKE",
        root_cause_confidence=0.70,
    )
    assert scorer.select(ctx) == RepairAction.ESCALATE


# ── GUARDED tier (GAP-A) ─────────────────────────────────────────────────────


def test_guarded_restart_ollama_selected() -> None:
    scorer = BestSolutionScorer()
    # RESTART_OLLAMA base=0.7030; adj=0.703*0.80 - 0.05 = 0.512 > 0.40
    ctx = BestSolutionContext(
        failure_reason="OLLAMA_PROCESS_DEAD",
        root_cause_confidence=0.80,
    )
    assert scorer.select(ctx) == RepairAction.RESTART_OLLAMA


def test_guarded_config_sync_selected() -> None:
    scorer = BestSolutionScorer()
    # CONFIG_SYNC base=0.6056; adj=0.6056*0.80 - 0.05 = 0.435 > 0.40
    ctx = BestSolutionContext(
        failure_reason="CONFIG_DRIFT_DETECTED",
        root_cause_confidence=0.80,
    )
    assert scorer.select(ctx) == RepairAction.CONFIG_SYNC


def test_guarded_recreate_container_selected() -> None:
    scorer = BestSolutionScorer()
    # RECREATE_CONTAINER base=0.592; adj=0.592*0.80 - 0.05 = 0.424 > 0.40
    ctx = BestSolutionContext(
        failure_reason="STATELESS_CONTAINER_DEAD",
        root_cause_confidence=0.80,
    )
    assert scorer.select(ctx) == RepairAction.RECREATE_CONTAINER


def test_guarded_crash_loop_escalates() -> None:
    scorer = BestSolutionScorer()
    ctx = BestSolutionContext(
        failure_reason="OLLAMA_PROCESS_DEAD",
        root_cause_confidence=0.85,
        restart_count=15,
        extra={"crash_loop_threshold": 10},
    )
    assert scorer.select(ctx) == RepairAction.ESCALATE


def test_guarded_low_confidence_above_gate_but_below_action_threshold_escalates() -> None:
    scorer = BestSolutionScorer()
    # rc_conf=0.45 > gate(0.40) but adj=0.703*0.45 - 0.05 = 0.266 < 0.40
    ctx = BestSolutionContext(
        failure_reason="OLLAMA_PROCESS_DEAD",
        root_cause_confidence=0.45,
    )
    assert scorer.select(ctx) == RepairAction.ESCALATE


# ── MANUAL_ONLY boundary ──────────────────────────────────────────────────────


def test_manual_only_crash_loop_always_escalates() -> None:
    scorer = BestSolutionScorer()
    ctx = BestSolutionContext(
        failure_reason="crash-loop",
        root_cause_confidence=0.95,
    )
    result = scorer.select(ctx)
    assert result == RepairAction.ESCALATE


def test_manual_only_unknown_reason_escalates() -> None:
    scorer = BestSolutionScorer()
    ctx = BestSolutionContext(
        failure_reason="TOTALLY_UNKNOWN_SIGNAL_XYZ",
        root_cause_confidence=0.95,
    )
    assert scorer.select(ctx) == RepairAction.ESCALATE


# ── high ambiguity via custom scorer ─────────────────────────────────────────


def test_high_ambiguity_reduces_score_below_threshold() -> None:
    scorer = BestSolutionScorer(scorer=_TwoCloseGUARDEDScorer())
    ctx = BestSolutionContext(
        failure_reason="ANY",
        root_cause_confidence=0.80,
    )
    # Two nearly identical GUARDED base scores → ambiguity ~1.0
    # → adjusted_score drops below GUARDED_AUTO_THRESHOLD → ESCALATE
    result = scorer.select(ctx)
    assert result == RepairAction.ESCALATE


# ── score_candidates ordering ─────────────────────────────────────────────────


def test_score_candidates_sorted_descending() -> None:
    scorer = BestSolutionScorer()
    ctx = BestSolutionContext(
        failure_reason="OLLAMA_PROCESS_DEAD",
        root_cause_confidence=0.80,
    )
    candidates = scorer.score_candidates(ctx)
    scores = [c.adjusted_score for c in candidates]
    assert scores == sorted(scores, reverse=True)


def test_score_candidates_restart_ollama_is_top() -> None:
    scorer = BestSolutionScorer()
    ctx = BestSolutionContext(
        failure_reason="OLLAMA_PROCESS_DEAD",
        root_cause_confidence=0.80,
    )
    candidates = scorer.score_candidates(ctx)
    assert candidates[0].action == RepairAction.RESTART_OLLAMA


def test_score_candidates_manual_only_marked_correctly() -> None:
    scorer = BestSolutionScorer()
    ctx = BestSolutionContext(
        failure_reason="OLLAMA_PROCESS_DEAD",
        root_cause_confidence=0.80,
    )
    candidates = scorer.score_candidates(ctx)
    for c in candidates:
        if c.action == RepairAction.ESCALATE:
            assert c.is_manual_only is True
        if c.action == RepairAction.RESTART_OLLAMA:
            assert c.is_manual_only is False
