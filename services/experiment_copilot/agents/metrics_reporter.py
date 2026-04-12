"""
services/experiment_copilot/agents/metrics_reporter.py — Metrics Reporter
IL-CEC-01 | banxe-emi-stack

Queries AML metrics from ClickHouse, compares vs baselines, and generates
experiment reports. Marks experiments FINISHED when conclusive.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable

import yaml

from services.experiment_copilot.models.experiment import (
    ComplianceExperiment,
    ExperimentStatus,
)
from services.experiment_copilot.models.metrics import (
    ExperimentMetrics,
    MetricsComparison,
    MetricTrend,
)
from services.experiment_copilot.store.audit_trail import AuditTrail
from services.experiment_copilot.store.experiment_store import ExperimentStore

logger = logging.getLogger("banxe.experiment_copilot.reporter")

_IMPROVEMENT_THRESHOLD = 0.10  # 10% improvement = "improving"
_REGRESSION_THRESHOLD = -0.05  # 5% regression = "regressing"


# ── ClickHouse Port (Protocol DI) ──────────────────────────────────────────


@runtime_checkable
class ClickHousePort(Protocol):
    def query(self, sql: str) -> list[dict[str, Any]]: ...


class InMemoryClickHousePort:
    """Test stub — returns deterministic metrics."""

    def query(self, sql: str) -> list[dict[str, Any]]:
        return [
            {
                "total_alerts": 120,
                "sar_count": 30,
                "hit_rate": 0.25,
                "false_positive_rate": 0.75,
                "sar_yield": 0.25,
                "avg_review_hours": 18.5,
                "amount_blocked_gbp": "45000.00",
                "cases_reviewed": 120,
            }
        ]


# ── Metrics Reporter ───────────────────────────────────────────────────────

_HIT_RATE_SQL = """\
SELECT
  count(*) AS total_alerts,
  countIf(outcome = 'SAR') AS sar_count,
  countIf(outcome = 'SAR') / count(*) AS hit_rate,
  countIf(outcome = 'FALSE_POSITIVE') / count(*) AS false_positive_rate,
  countIf(outcome = 'SAR') / count(*) AS sar_yield,
  avg(review_duration_hours) AS avg_review_hours,
  sum(amount_gbp) AS amount_blocked_gbp,
  count(*) AS cases_reviewed
FROM banxe.aml_alerts
WHERE created_at >= now() - INTERVAL {days} DAY
"""


class MetricsReporter:
    """Generates AML performance reports for compliance experiments.

    Queries ClickHouse for actual metrics, compares vs baseline/target,
    and classifies the trend as IMPROVING / REGRESSING / INCONCLUSIVE.
    """

    def __init__(
        self,
        store: ExperimentStore,
        audit: AuditTrail,
        clickhouse: ClickHousePort | None = None,
        baselines_path: str = "config/aml_baselines.yaml",
    ) -> None:
        self._store = store
        self._audit = audit
        self._ch = clickhouse or InMemoryClickHousePort()
        self._baselines = self._load_baselines(baselines_path)

    def get_current_metrics(self, period_days: int = 1) -> ExperimentMetrics:
        """Query ClickHouse for current AML metrics."""
        sql = _HIT_RATE_SQL.format(days=period_days)
        rows = self._ch.query(sql)
        if not rows:
            return ExperimentMetrics(period_days=period_days)

        row = rows[0]
        return ExperimentMetrics(
            hit_rate_24h=row.get("hit_rate"),
            false_positive_rate=row.get("false_positive_rate"),
            sar_yield=row.get("sar_yield"),
            time_to_review_hours=row.get("avg_review_hours"),
            amount_blocked_gbp=Decimal(str(row["amount_blocked_gbp"]))
            if row.get("amount_blocked_gbp")
            else None,
            cases_reviewed=row.get("cases_reviewed", 0),
            period_days=period_days,
        )

    def compare(self, experiment: ComplianceExperiment, period_days: int = 7) -> MetricsComparison:
        """Compare actual metrics vs experiment baseline and target."""
        actual = self.get_current_metrics(period_days)
        trend, improvement_pct = self._classify_trend(
            actual, experiment.metrics_baseline, experiment.metrics_target
        )
        narrative = self._build_narrative(actual, experiment, trend, improvement_pct)
        recommendation = self._recommend(trend, improvement_pct)

        return MetricsComparison(
            experiment_id=experiment.id,
            period_days=period_days,
            baseline=experiment.metrics_baseline,
            target=experiment.metrics_target,
            actual=actual,
            trend=trend,
            improvement_pct=improvement_pct,
            narrative=narrative,
            recommendation=recommendation,
        )

    def generate_report(self, experiment: ComplianceExperiment, period_days: int = 7) -> str:
        """Generate a markdown report for an experiment."""
        comparison = self.compare(experiment, period_days)
        actual = comparison.actual

        lines = [
            f"# Experiment Report: {experiment.title}",
            f"**ID**: `{experiment.id}` | **Period**: {period_days} days",
            f"**Trend**: {comparison.trend.value.upper()} "
            f"({comparison.improvement_pct:.1%} improvement)"
            if comparison.improvement_pct is not None
            else f"**Trend**: {comparison.trend.value.upper()}",
            "",
            "## Metrics",
            "| Metric | Baseline | Target | Actual | Status |",
            "|--------|----------|--------|--------|--------|",
        ]

        for metric, baseline_key in [
            ("Hit Rate 24h", "hit_rate_24h"),
            ("False Positive Rate", "false_positive_rate"),
            ("SAR Yield", "sar_yield"),
        ]:
            b = experiment.metrics_baseline.get(baseline_key, "N/A")
            t = experiment.metrics_target.get(baseline_key, "N/A")
            a = getattr(actual, baseline_key, None)
            a_str = f"{a:.2%}" if a is not None else "N/A"
            status = self._metric_status(a, t)
            lines.append(f"| {metric} | {b} | {t} | {a_str} | {status} |")

        lines += [
            "",
            "## Narrative",
            comparison.narrative,
            "",
            f"## Recommendation: **{comparison.recommendation.upper()}**",
            "",
            f"_Citations: {', '.join(experiment.kb_citations) or 'none'}_",
        ]

        self._audit.log(
            actor="metrics-reporter",
            action="experiment.report.generated",
            experiment_id=experiment.id,
            details={
                "trend": comparison.trend.value,
                "improvement_pct": comparison.improvement_pct,
                "recommendation": comparison.recommendation,
            },
        )
        return "\n".join(lines)

    def auto_finish_if_conclusive(
        self, experiment: ComplianceExperiment, period_days: int = 14
    ) -> bool:
        """Move experiment to FINISHED if metrics are conclusive (>10% improvement)."""
        if experiment.status != ExperimentStatus.ACTIVE:
            return False
        comparison = self.compare(experiment, period_days)
        if comparison.trend == MetricTrend.IMPROVING and period_days >= 14:
            experiment.status = ExperimentStatus.FINISHED
            experiment.metrics_actual = comparison.actual.model_dump(mode="json")
            self._store.save(experiment)
            self._audit.log(
                actor="metrics-reporter",
                action="experiment.auto_finished",
                experiment_id=experiment.id,
                details={"trend": comparison.trend.value, "period_days": period_days},
            )
            logger.info("Auto-finished experiment %s (trend: IMPROVING)", experiment.id)
            return True
        return False

    # ── Internal ───────────────────────────────────────────────────────────

    def _classify_trend(
        self,
        actual: ExperimentMetrics,
        baseline: dict[str, Any],
        target: dict[str, Any],
    ) -> tuple[MetricTrend, float | None]:
        key_metric = "hit_rate_24h"
        b = baseline.get(key_metric)
        a = actual.hit_rate_24h

        if a is None or b is None:
            return MetricTrend.INCONCLUSIVE, None

        if b == 0:
            return MetricTrend.INCONCLUSIVE, None

        improvement_pct = (a - b) / abs(b)
        if improvement_pct >= _IMPROVEMENT_THRESHOLD:
            return MetricTrend.IMPROVING, improvement_pct
        if improvement_pct <= _REGRESSION_THRESHOLD:
            return MetricTrend.REGRESSING, improvement_pct
        return MetricTrend.INCONCLUSIVE, improvement_pct

    def _build_narrative(
        self,
        actual: ExperimentMetrics,
        experiment: ComplianceExperiment,
        trend: MetricTrend,
        improvement_pct: float | None,
    ) -> str:
        hit = f"{actual.hit_rate_24h:.1%}" if actual.hit_rate_24h is not None else "N/A"
        fp = (
            f"{actual.false_positive_rate:.1%}" if actual.false_positive_rate is not None else "N/A"
        )
        imp_str = f" ({improvement_pct:+.1%} vs baseline)" if improvement_pct is not None else ""
        return (
            f"Experiment '{experiment.title}' shows {trend.value} trend{imp_str}. "
            f"Current hit rate: {hit} (target: {experiment.metrics_target.get('hit_rate_24h', 'N/A')}). "
            f"False positive rate: {fp}. "
            f"Cases reviewed: {actual.cases_reviewed}."
        )

    @staticmethod
    def _recommend(trend: MetricTrend, improvement_pct: float | None) -> str:
        if trend == MetricTrend.IMPROVING:
            return "continue"
        if trend == MetricTrend.REGRESSING:
            return "stop"
        return "extend"

    @staticmethod
    def _metric_status(actual: float | None, target: Any) -> str:
        if actual is None or target is None:
            return "⬜ N/A"
        try:
            t = float(target)  # nosemgrep: banxe-float-money — target is a rate, not monetary
        except (ValueError, TypeError):
            return "⬜ N/A"
        if actual >= t:
            return "✅ MET"
        if actual >= t * 0.8:
            return "🟡 CLOSE"
        return "❌ MISS"

    def _load_baselines(self, path: str) -> dict[str, Any]:
        from pathlib import Path as P

        p = P(path)
        if not p.exists():
            return {}
        with open(p, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
