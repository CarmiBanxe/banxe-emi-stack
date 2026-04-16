"""
services/audit_dashboard/risk_scorer.py
IL-AGD-01 | Phase 16

Multi-dimensional risk scoring: AML + fraud + operational + regulatory.
Each score 0–100 float. Higher = higher risk.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from services.audit_dashboard.models import (
    EventStorePort,
    RiskEnginePort,
    RiskLevel,
    RiskScore,
)

# Boundaries for risk categorisation
_LOW_MAX = 25.0
_MEDIUM_MAX = 50.0
_HIGH_MAX = 75.0


class RiskScorer:
    """Orchestrates multi-dimensional risk scoring for entities."""

    def __init__(
        self,
        engine: RiskEnginePort,
        store: EventStorePort,
    ) -> None:
        self._engine = engine
        self._store = store

    async def score_entity(self, entity_id: str, lookback_days: int = 30) -> RiskScore:
        """Compute a RiskScore for one entity using events within lookback window."""
        to_dt = datetime.now(UTC)
        from_dt = to_dt - timedelta(days=lookback_days)

        events = await self._store.query_events(
            entity_id=entity_id,
            from_dt=from_dt,
            to_dt=to_dt,
            limit=10_000,
        )
        return await self._engine.compute_score(entity_id=entity_id, events=events)

    async def score_batch(self, entity_ids: list[str], lookback_days: int = 30) -> list[RiskScore]:
        """Score a batch of entities sequentially; empty input returns []."""
        results: list[RiskScore] = []
        for eid in entity_ids:
            score = await self.score_entity(eid, lookback_days=lookback_days)
            results.append(score)
        return results

    async def get_high_risk_entities(
        self, threshold: float = 75.0, lookback_days: int = 30
    ) -> list[RiskScore]:
        """
        Return entities whose overall_score >= threshold.

        For InMemory store this requires pre-known entity IDs — returns [] by default.
        Real implementation would query an index.
        """
        return []

    def categorise_risk(self, score: RiskScore) -> RiskLevel:
        """Map overall_score to RiskLevel bucket."""
        if score.overall_score < _LOW_MAX:
            return RiskLevel.LOW
        if score.overall_score < _MEDIUM_MAX:
            return RiskLevel.MEDIUM
        if score.overall_score < _HIGH_MAX:
            return RiskLevel.HIGH
        return RiskLevel.CRITICAL

    async def get_risk_summary(self, entity_ids: list[str]) -> dict:
        """
        Score all entities and return summary counts by RiskLevel.

        Returns: {total, by_level: {LOW: N, MEDIUM: N, HIGH: N, CRITICAL: N}}
        """
        by_level: dict[str, int] = {
            RiskLevel.LOW.value: 0,
            RiskLevel.MEDIUM.value: 0,
            RiskLevel.HIGH.value: 0,
            RiskLevel.CRITICAL.value: 0,
        }

        if not entity_ids:
            return {"total": 0, "by_level": by_level}

        scores = await self.score_batch(entity_ids)
        for score in scores:
            level = self.categorise_risk(score)
            by_level[level.value] += 1

        return {"total": len(scores), "by_level": by_level}


__all__ = ["RiskScorer"]
