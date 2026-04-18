"""
services/risk_management/risk_aggregator.py
IL-RMS-01 | Phase 37 | banxe-emi-stack

Risk Aggregator — portfolio heatmap, concentration analysis, top risks.
I-01: All scores as Decimal.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import uuid

from services.risk_management.models import (
    AssessmentPort,
    AssessmentStatus,
    InMemoryAssessmentPort,
    InMemoryRiskScorePort,
    RiskAssessment,
    RiskLevel,
    RiskScore,
    RiskScorePort,
)
from services.risk_management.risk_scorer import RiskScorer


class RiskAggregator:
    """Aggregates risk scores into assessments, heatmaps, and portfolio analysis."""

    def __init__(
        self,
        score_store: RiskScorePort | None = None,
        assessment_store: AssessmentPort | None = None,
    ) -> None:
        self._score_store: RiskScorePort = score_store or InMemoryRiskScorePort()
        self._assessment_store: AssessmentPort = assessment_store or InMemoryAssessmentPort()
        self._scorer = RiskScorer(self._score_store)

    def aggregate_entity(self, entity_id: str) -> RiskAssessment:
        """Pull all RiskScores for entity, compute aggregate, create RiskAssessment."""
        scores = self._score_store.get_scores(entity_id)
        aggregate = self._scorer.compute_aggregate(scores)

        assessment = RiskAssessment(
            id=str(uuid.uuid4()),
            entity_id=entity_id,
            status=AssessmentStatus.COMPLETED,
            scores=scores,
            aggregate_score=aggregate,
            created_at=datetime.now(UTC),
            due_date=datetime.now(UTC),
            assessor_id="system",
        )
        self._assessment_store.save_assessment(assessment)
        return assessment

    def portfolio_heatmap(self, entity_ids: list[str]) -> dict:
        """Return {entity_id: {category: level}} heat map."""
        heatmap: dict[str, dict[str, str]] = {}
        for entity_id in entity_ids:
            scores = self._score_store.get_scores(entity_id)
            heatmap[entity_id] = {s.category.value: s.level.value for s in scores}
        return heatmap

    def concentration_analysis(self) -> dict:
        """Count entities per RiskLevel, flag if >20% in HIGH/CRITICAL."""
        all_scores = self._score_store.list_all()
        entity_levels: dict[str, RiskLevel] = {}

        for s in all_scores:
            existing = entity_levels.get(s.entity_id)
            level_order = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]
            if existing is None or level_order.index(s.level) > level_order.index(existing):
                entity_levels[s.entity_id] = s.level

        counts: dict[str, int] = {lvl.value: 0 for lvl in RiskLevel}
        for lvl in entity_levels.values():
            counts[lvl.value] += 1

        total = len(entity_levels)
        high_critical = counts[RiskLevel.HIGH.value] + counts[RiskLevel.CRITICAL.value]
        if total > 0:
            pct = Decimal(high_critical) / Decimal(total)
            flagged = pct > Decimal("0.20")
            pct_str = str((pct * Decimal("100")).quantize(Decimal("0.01")))
        else:
            flagged = False
            pct_str = "0.00"

        return {
            "total_entities": total,
            "distribution": counts,
            "high_critical_pct": pct_str,
            "concentration_flag": flagged,
        }

    def get_top_risks(self, n: int = 10) -> list[RiskScore]:
        """Return top N scores by score value descending."""
        all_scores = self._score_store.list_all()
        return sorted(all_scores, key=lambda s: s.score, reverse=True)[:n]
