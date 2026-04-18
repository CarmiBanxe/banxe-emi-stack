"""
services/risk_management/risk_scorer.py
IL-RMS-01 | Phase 37 | banxe-emi-stack

Risk Scoring Engine — weighted average, level classification, batch scoring.
I-01: All scores as Decimal (never float).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import uuid

from services.risk_management.models import (
    InMemoryRiskScorePort,
    RiskCategory,
    RiskLevel,
    RiskScore,
    RiskScorePort,
    ScoreModel,
)

DEFAULT_WEIGHTS: dict[RiskCategory, Decimal] = {
    RiskCategory.CREDIT: Decimal("0.25"),
    RiskCategory.OPERATIONAL: Decimal("0.20"),
    RiskCategory.AML: Decimal("0.30"),
    RiskCategory.FRAUD: Decimal("0.15"),
    RiskCategory.MARKET: Decimal("0.10"),
}

_ZERO = Decimal("0")
_HUNDRED = Decimal("100")


class RiskScorer:
    """Core risk scoring engine for entity risk assessment."""

    def __init__(self, store: RiskScorePort | None = None) -> None:
        self._store: RiskScorePort = store or InMemoryRiskScorePort()

    def score_entity(
        self,
        entity_id: str,
        factors: dict[str, Decimal],
        category: RiskCategory,
        model: ScoreModel = ScoreModel.WEIGHTED_AVERAGE,
        assessed_by: str = "system",
    ) -> RiskScore:
        """Score an entity for a given risk category using factor weights."""
        weights = DEFAULT_WEIGHTS
        weight = weights.get(category, Decimal("0.10"))

        if factors:
            raw = sum(Decimal(str(v)) for v in factors.values()) * weight
        else:
            raw = _ZERO

        score = max(_ZERO, min(_HUNDRED, raw))
        level = self.classify_level(score)

        risk_score = RiskScore(
            id=str(uuid.uuid4()),
            entity_id=entity_id,
            category=category,
            score=score,
            level=level,
            model=model,
            factors={k: str(v) for k, v in factors.items()},
            assessed_at=datetime.now(UTC),
            assessed_by=assessed_by,
        )
        self._store.save_score(risk_score)
        return risk_score

    def compute_aggregate(
        self,
        scores: list[RiskScore],
        weights: dict[RiskCategory, Decimal] | None = None,
    ) -> Decimal:
        """Compute weighted average aggregate score across categories."""
        if not scores:
            return _ZERO

        w = weights or DEFAULT_WEIGHTS
        total_weight = _ZERO
        weighted_sum = _ZERO

        for s in scores:
            cat_weight = w.get(s.category, Decimal("0.10"))
            weighted_sum += s.score * cat_weight
            total_weight += cat_weight

        if total_weight == _ZERO:
            return _ZERO

        return max(_ZERO, min(_HUNDRED, weighted_sum / total_weight))

    def classify_level(self, score: Decimal) -> RiskLevel:
        """Classify score into risk level: LOW<25, MEDIUM<50, HIGH<75, CRITICAL>=75."""
        if score < Decimal("25"):
            return RiskLevel.LOW
        if score < Decimal("50"):
            return RiskLevel.MEDIUM
        if score < Decimal("75"):
            return RiskLevel.HIGH
        return RiskLevel.CRITICAL

    def batch_score(self, entities: list[dict]) -> list[RiskScore]:
        """Score a list of entities in one call.

        Each dict must have: entity_id, factors, category.
        Optional: model, assessed_by.
        """
        results: list[RiskScore] = []
        for entity in entities:
            score = self.score_entity(
                entity_id=entity["entity_id"],
                factors={k: Decimal(str(v)) for k, v in entity.get("factors", {}).items()},
                category=RiskCategory(entity["category"]),
                model=ScoreModel(entity.get("model", ScoreModel.WEIGHTED_AVERAGE.value)),
                assessed_by=entity.get("assessed_by", "system"),
            )
            results.append(score)
        return results
