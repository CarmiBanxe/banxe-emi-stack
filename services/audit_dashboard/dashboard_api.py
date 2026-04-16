"""
services/audit_dashboard/dashboard_api.py
IL-AGD-01 | Phase 16

Dashboard state service: aggregates live metrics for the governance dashboard.
WebSocket broadcast managed here; HTTP polling also supported.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from services.audit_dashboard.audit_aggregator import AuditAggregator
from services.audit_dashboard.governance_reporter import GovernanceReporter
from services.audit_dashboard.models import (
    DashboardMetrics,
    MetricsStorePort,
)
from services.audit_dashboard.risk_scorer import RiskScorer


class DashboardService:
    """Aggregates live governance metrics and risk matrix for the dashboard."""

    def __init__(
        self,
        aggregator: AuditAggregator,
        scorer: RiskScorer,
        reporter: GovernanceReporter,
        metrics_store: MetricsStorePort,
    ) -> None:
        self._aggregator = aggregator
        self._scorer = scorer
        self._reporter = reporter
        self._metrics_store = metrics_store

    async def get_live_metrics(self) -> DashboardMetrics:
        """
        Fetch base metrics from store and augment with live event counts
        from the aggregator (last 24 h).
        """
        base = await self._metrics_store.get_dashboard_metrics()

        to_dt = datetime.now(UTC)
        from_dt = to_dt - timedelta(hours=24)
        summary = await self._aggregator.get_event_summary(from_dt, to_dt)

        return DashboardMetrics(
            generated_at=datetime.now(UTC),
            total_events_24h=summary["total"] or base.total_events_24h,
            high_risk_events=summary["high_risk_count"] or base.high_risk_events,
            compliance_score=base.compliance_score,
            active_consents=base.active_consents,
            pending_hitl=base.pending_hitl,
            safeguarding_status=base.safeguarding_status,
            risk_by_category=summary.get("by_category") or base.risk_by_category,
        )

    async def get_risk_matrix(self, entity_ids: list[str]) -> list[dict]:
        """
        Score each entity and return a matrix row per entity.

        Each row: {entity_id, risk_level, overall_score, factors}
        """
        matrix: list[dict] = []
        for eid in entity_ids:
            score = await self._scorer.score_entity(eid)
            risk_level = self._scorer.categorise_risk(score)
            matrix.append(
                {
                    "entity_id": eid,
                    "risk_level": risk_level.value,
                    "overall_score": score.overall_score,
                    "factors": score.contributing_factors,
                }
            )
        return matrix

    async def get_governance_status(self) -> dict:
        """Return governance status with timestamp and details."""
        status = await self._reporter.get_compliance_status()
        return {
            "status": status.value,
            "checked_at": datetime.now(UTC).isoformat(),
            "details": f"Governance status computed at {datetime.now(UTC).isoformat()}",
        }


__all__ = ["DashboardService"]
