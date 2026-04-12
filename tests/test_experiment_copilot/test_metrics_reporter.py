"""
tests/test_experiment_copilot/test_metrics_reporter.py
IL-CEC-01 | banxe-emi-stack

Tests for MetricsReporter: get_current_metrics(), compare(), generate_report(),
_classify_trend(), auto_finish_if_conclusive(), and _metric_status().
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from services.experiment_copilot.agents.metrics_reporter import (
    InMemoryClickHousePort,
    MetricsReporter,
)
from services.experiment_copilot.models.experiment import (
    ComplianceExperiment,
    ExperimentScope,
    ExperimentStatus,
)
from services.experiment_copilot.models.metrics import MetricTrend
from services.experiment_copilot.store.audit_trail import AuditTrail
from services.experiment_copilot.store.experiment_store import ExperimentStore


def _make_active_experiment(
    exp_id: str = "exp-2026-04-metrics-test",
    hit_rate_baseline: float = 0.20,
    hit_rate_target: float = 0.35,
) -> ComplianceExperiment:
    return ComplianceExperiment(
        id=exp_id,
        title="Hit Rate Improvement",
        scope=ExperimentScope.TRANSACTION_MONITORING,
        status=ExperimentStatus.ACTIVE,
        hypothesis="By tuning thresholds, we expect to improve hit rate significantly.",
        kb_citations=["eba-gl-2021-02"],
        created_by="analyst@banxe.com",
        metrics_baseline={"hit_rate_24h": hit_rate_baseline, "false_positive_rate": 0.75},
        metrics_target={"hit_rate_24h": hit_rate_target, "false_positive_rate": 0.60},
    )


def _make_reporter(tmp_path: Path) -> MetricsReporter:
    store = ExperimentStore(experiments_dir=str(tmp_path / "experiments"))
    audit = AuditTrail(log_path=str(tmp_path / "audit.jsonl"))
    return MetricsReporter(
        store=store,
        audit=audit,
        clickhouse=InMemoryClickHousePort(),
    )


class TestGetCurrentMetrics:
    def test_get_current_metrics_returns_valid_object(self, tmp_path):
        reporter = _make_reporter(tmp_path)
        metrics = reporter.get_current_metrics(period_days=1)
        assert metrics.period_days == 1
        assert metrics.hit_rate_24h is not None
        assert 0.0 <= metrics.hit_rate_24h <= 1.0

    def test_amount_blocked_is_decimal(self, tmp_path):
        reporter = _make_reporter(tmp_path)
        metrics = reporter.get_current_metrics(period_days=1)
        if metrics.amount_blocked_gbp is not None:
            assert isinstance(metrics.amount_blocked_gbp, Decimal)


class TestClassifyTrend:
    def test_improving_trend_when_above_threshold(self, tmp_path):
        reporter = _make_reporter(tmp_path)
        # InMemoryClickHousePort returns hit_rate=0.25, baseline=0.20 → +25% improvement
        exp = _make_active_experiment(hit_rate_baseline=0.20)
        comparison = reporter.compare(exp, period_days=14)
        assert comparison.trend == MetricTrend.IMPROVING
        assert comparison.improvement_pct is not None
        assert comparison.improvement_pct > 0.10

    def test_regressing_trend_when_below_threshold(self, tmp_path):
        reporter = _make_reporter(tmp_path)
        # baseline=0.40, actual=0.25 → -37.5% (well below -5% regression threshold)
        exp = _make_active_experiment(hit_rate_baseline=0.40)
        comparison = reporter.compare(exp, period_days=7)
        assert comparison.trend == MetricTrend.REGRESSING

    def test_inconclusive_when_zero_baseline(self, tmp_path):
        reporter = _make_reporter(tmp_path)
        exp = _make_active_experiment(hit_rate_baseline=0.0)
        comparison = reporter.compare(exp, period_days=7)
        assert comparison.trend == MetricTrend.INCONCLUSIVE


class TestGenerateReport:
    def test_generate_report_returns_markdown(self, tmp_path):
        reporter = _make_reporter(tmp_path)
        exp = _make_active_experiment()
        report = reporter.generate_report(exp, period_days=7)
        assert "# Experiment Report" in report
        assert "Hit Rate" in report
        assert "## Recommendation" in report

    def test_generate_report_includes_experiment_id(self, tmp_path):
        reporter = _make_reporter(tmp_path)
        exp = _make_active_experiment("exp-report-id-test")
        report = reporter.generate_report(exp, period_days=7)
        assert "exp-report-id-test" in report

    def test_generate_report_logs_audit(self, tmp_path):
        reporter = _make_reporter(tmp_path)
        exp = _make_active_experiment("exp-report-audit")
        reporter.generate_report(exp, period_days=7)
        audit = AuditTrail(log_path=str(tmp_path / "audit.jsonl"))
        entries = audit.get_entries("exp-report-audit")
        assert any(e.action == "experiment.report.generated" for e in entries)


class TestAutoFinish:
    def test_auto_finish_improving_experiment(self, tmp_path):
        reporter = _make_reporter(tmp_path)
        store = ExperimentStore(experiments_dir=str(tmp_path / "experiments"))
        exp = _make_active_experiment("exp-auto-finish")
        # InMemory returns hit_rate=0.25, baseline=0.20 → IMPROVING
        store.save(exp)
        reporter._store = store
        result = reporter.auto_finish_if_conclusive(exp, period_days=14)
        assert result is True
        assert exp.status == ExperimentStatus.FINISHED

    def test_auto_finish_does_not_finish_regressing(self, tmp_path):
        reporter = _make_reporter(tmp_path)
        store = ExperimentStore(experiments_dir=str(tmp_path / "experiments"))
        exp = _make_active_experiment("exp-no-finish", hit_rate_baseline=0.40)
        store.save(exp)
        reporter._store = store
        result = reporter.auto_finish_if_conclusive(exp, period_days=14)
        assert result is False
        assert exp.status == ExperimentStatus.ACTIVE
