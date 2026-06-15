"""ConfidenceScorer — deterministic bands across match_source / risk / ambiguity."""

from __future__ import annotations

import pytest

from services.intent_layer.models import ConfidenceBand, MatchSource
from services.producers.confidence_scorer import ConfidenceScorer, ScoringSignals


@pytest.fixture
def scorer() -> ConfidenceScorer:
    return ConfidenceScorer()


@pytest.mark.parametrize(
    ("match_source", "expected"),
    [
        (MatchSource.EXACT, 1.0),
        (MatchSource.ALIAS, 0.95),
        (MatchSource.LLM, 0.75),
        (MatchSource.NONE, 0.0),
    ],
)
def test_base_by_match_source(
    scorer: ConfidenceScorer, match_source: MatchSource, expected: float
) -> None:
    assert scorer.score(ScoringSignals(match_source=match_source)) == expected


def test_unresolved_scores_zero(scorer: ConfidenceScorer) -> None:
    signals = ScoringSignals(match_source=MatchSource.EXACT, resolved=False)
    assert scorer.score(signals) == 0.0
    assert scorer.band(signals) is ConfidenceBand.BLOCK


def test_high_risk_penalty_drops_band(scorer: ConfidenceScorer) -> None:
    signals = ScoringSignals(match_source=MatchSource.LLM, risk_class="HIGH")
    assert scorer.score(signals) == 0.60  # 0.75 - 0.15
    assert scorer.band(signals) is ConfidenceBand.BLOCK


def test_elevated_risk_penalty(scorer: ConfidenceScorer) -> None:
    signals = ScoringSignals(match_source=MatchSource.ALIAS, risk_class="elevated")
    assert scorer.score(signals) == 0.90  # 0.95 - 0.05 ; case-insensitive


def test_ambiguity_penalty_clamped(scorer: ConfidenceScorer) -> None:
    # ambiguity > 1 is clamped to 1 → max 0.20 penalty.
    signals = ScoringSignals(match_source=MatchSource.EXACT, ambiguity=5.0)
    assert scorer.score(signals) == 0.80


def test_unknown_risk_class_no_penalty(scorer: ConfidenceScorer) -> None:
    signals = ScoringSignals(match_source=MatchSource.EXACT, risk_class="WEIRD")
    assert scorer.score(signals) == 1.0


def test_band_thresholds(scorer: ConfidenceScorer) -> None:
    assert scorer.band(ScoringSignals(MatchSource.EXACT)) is ConfidenceBand.AUTO
    assert scorer.band(ScoringSignals(MatchSource.LLM)) is ConfidenceBand.REVIEW
    assert scorer.band(ScoringSignals(MatchSource.NONE)) is ConfidenceBand.BLOCK


def test_negative_ambiguity_clamped(scorer: ConfidenceScorer) -> None:
    signals = ScoringSignals(match_source=MatchSource.EXACT, ambiguity=-3.0)
    assert scorer.score(signals) == 1.0


def test_from_resolved_intent() -> None:
    from services.intent_layer.models import IntentStatus, ResolvedIntent

    ri = ResolvedIntent(
        raw_text="show my balance",
        correlation_id="c1",
        status=IntentStatus.RESOLVED,
        confidence=1.0,
        match_source=MatchSource.EXACT,
    )
    signals = ScoringSignals.from_resolved_intent(ri, risk_class="ELEVATED")
    assert signals.match_source is MatchSource.EXACT
    assert signals.resolved is True
    assert signals.risk_class == "ELEVATED"
    assert ConfidenceScorer().score(signals) == 0.95
