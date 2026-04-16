"""
services/audit_dashboard/governance_reporter.py
IL-AGD-01 | Phase 16

Generates governance and compliance reports (JSON + PDF summary).
Used by board reporting and FCA submissions (SYSC 9 compliance).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import uuid

from services.audit_dashboard.audit_aggregator import AuditAggregator
from services.audit_dashboard.models import (
    GovernanceReport,
    GovernanceStatus,
    ReportFormat,
    ReportStorePort,
    RiskLevel,
)
from services.audit_dashboard.risk_scorer import RiskScorer


class GovernanceReporter:
    """Creates, stores, and queries governance/compliance reports."""

    def __init__(
        self,
        aggregator: AuditAggregator,
        scorer: RiskScorer,
        report_store: ReportStorePort,
    ) -> None:
        self._aggregator = aggregator
        self._scorer = scorer
        self._store = report_store

    async def generate_report(
        self,
        title: str,
        period_start: datetime,
        period_end: datetime,
        entity_ids: list[str] | None = None,
        actor: str = "system",
    ) -> GovernanceReport:
        """
        Generate a GovernanceReport for the given period.

        compliance_score = 100 – (high_risk_events / total * 100), clamped 0–100.
        """
        summary = await self._aggregator.get_event_summary(period_start, period_end)
        total: int = summary["total"]
        high_risk: int = summary["high_risk_count"]

        if total > 0:
            raw_score = 100.0 - (high_risk / total * 100.0)
        else:
            raw_score = 100.0
        compliance_score = max(0.0, min(100.0, raw_score))

        entity_scores: list[dict] = []
        if entity_ids:
            scores = await self._scorer.score_batch(entity_ids)
            for s in scores:
                entity_scores.append(
                    {
                        "entity_id": s.entity_id,
                        "overall_score": s.overall_score,
                        "risk_level": self._scorer.categorise_risk(s).value,
                    }
                )

        content: dict = {
            "actor": actor,
            "event_summary": summary,
            "entity_scores": entity_scores,
        }

        report = GovernanceReport(
            id=str(uuid.uuid4()),
            title=title,
            period_start=period_start,
            period_end=period_end,
            generated_at=datetime.now(UTC),
            format=ReportFormat.JSON,
            content=content,
            total_events=total,
            risk_summary=summary.get("by_risk_level", {}),
            compliance_score=round(compliance_score, 2),
        )
        await self._store.save_report(report)
        return report

    async def get_report(self, report_id: str) -> GovernanceReport | None:
        """Retrieve a previously saved report by ID."""
        return await self._store.get_report(report_id)

    async def list_reports(self, limit: int = 20) -> list[GovernanceReport]:
        """List stored reports (most recently saved first)."""
        return await self._store.list_reports(limit=limit)

    async def get_compliance_status(self) -> GovernanceStatus:
        """
        Compute overall governance status from the last 24 h of events.

        COMPLIANT            — no high-risk events
        REQUIRES_ATTENTION   — some HIGH events (but no CRITICAL)
        NON_COMPLIANT        — any CRITICAL events
        """
        to_dt = datetime.now(UTC)
        from_dt = to_dt - timedelta(hours=24)

        critical_events = await self._aggregator.query_events(
            from_dt=from_dt,
            to_dt=to_dt,
            risk_level=RiskLevel.CRITICAL,
            limit=1,
        )
        if critical_events:
            return GovernanceStatus.NON_COMPLIANT

        high_events = await self._aggregator.query_events(
            from_dt=from_dt,
            to_dt=to_dt,
            risk_level=RiskLevel.HIGH,
            limit=1,
        )
        if high_events:
            return GovernanceStatus.REQUIRES_ATTENTION

        return GovernanceStatus.COMPLIANT


__all__ = ["GovernanceReporter"]
