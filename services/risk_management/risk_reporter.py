"""
services/risk_management/risk_reporter.py
IL-RMS-01 | Phase 37 | banxe-emi-stack

Risk Reporter — generate reports, export JSON, board summaries, trend data.
I-01: All scores as Decimal.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
import json
import uuid

from services.risk_management.models import (
    InMemoryRiskScorePort,
    RiskCategory,
    RiskLevel,
    RiskReport,
    RiskScorePort,
)


class _DecimalEncoder(json.JSONEncoder):
    def default(self, o: object) -> object:
        if isinstance(o, Decimal):
            return str(o)
        if isinstance(o, datetime):
            return o.isoformat()
        return super().default(o)


class RiskReporter:
    """Generates risk reports with distribution analysis and trend data."""

    def __init__(self, store: RiskScorePort | None = None) -> None:
        self._store: RiskScorePort = store or InMemoryRiskScorePort()

    def generate_report(
        self,
        scope: str,
        period_start: date,
        period_end: date,
    ) -> RiskReport:
        """Aggregate all scores and build distribution dict with top 5 risks."""
        all_scores = self._store.list_all()

        entity_ids = list({s.entity_id for s in all_scores})
        total_entities = len(entity_ids)

        distribution: dict[str, int] = {lvl.value: 0 for lvl in RiskLevel}
        for s in all_scores:
            distribution[s.level.value] += 1

        top_risks = sorted(all_scores, key=lambda s: s.score, reverse=True)[:5]
        top_risks_data = [
            {
                "entity_id": s.entity_id,
                "category": s.category.value,
                "score": str(s.score),
                "level": s.level.value,
            }
            for s in top_risks
        ]

        return RiskReport(
            id=str(uuid.uuid4()),
            generated_at=datetime.now(UTC),
            scope=scope,
            total_entities=total_entities,
            distribution=distribution,
            top_risks=top_risks_data,
            period_start=datetime(
                period_start.year, period_start.month, period_start.day, tzinfo=UTC
            ),
            period_end=datetime(period_end.year, period_end.month, period_end.day, tzinfo=UTC),
        )

    def export_json(self, report: RiskReport) -> str:
        """Serialize report to JSON with Decimal serialization."""
        data = {
            "id": report.id,
            "generated_at": report.generated_at.isoformat(),
            "scope": report.scope,
            "total_entities": report.total_entities,
            "distribution": report.distribution,
            "top_risks": report.top_risks,
            "period_start": report.period_start.isoformat(),
            "period_end": report.period_end.isoformat(),
        }
        return json.dumps(data, cls=_DecimalEncoder, indent=2)

    def export_summary(self, report: RiskReport) -> dict:
        """Board-level summary: total, by level count, highest risk entity."""
        highest_entity: str | None = None
        highest_score = Decimal("0")

        all_scores = self._store.list_all()
        for s in all_scores:
            if s.score > highest_score:
                highest_score = s.score
                highest_entity = s.entity_id

        return {
            "total_entities": report.total_entities,
            "distribution": report.distribution,
            "highest_risk_entity": highest_entity,
            "highest_risk_score": str(highest_score),
            "scope": report.scope,
            "generated_at": report.generated_at.isoformat(),
        }

    def get_trend(self, category: RiskCategory, days: int = 30) -> list[dict]:
        """Return [{date, avg_score}] trend data (stub: returns empty if no history)."""
        return []
