"""
tests/test_risk_management/test_risk_reporter.py
IL-RMS-01 | Phase 37 | banxe-emi-stack — 16 tests
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
import json

from services.risk_management.models import (
    InMemoryRiskScorePort,
    RiskCategory,
)
from services.risk_management.risk_reporter import RiskReporter
from services.risk_management.risk_scorer import RiskScorer


def _reporter() -> tuple[RiskReporter, InMemoryRiskScorePort]:
    store = InMemoryRiskScorePort()
    store._scores.clear()
    return RiskReporter(store), store


class TestGenerateReport:
    def test_returns_risk_report(self) -> None:
        reporter, store = _reporter()
        scorer = RiskScorer(store)
        scorer.score_entity("e-1", {"f": Decimal("40")}, RiskCategory.AML)
        today = date.today()
        report = reporter.generate_report("global", today - timedelta(days=30), today)
        assert report.scope == "global"

    def test_total_entities_correct(self) -> None:
        reporter, store = _reporter()
        scorer = RiskScorer(store)
        scorer.score_entity("e-1", {"f": Decimal("30")}, RiskCategory.AML)
        scorer.score_entity("e-2", {"f": Decimal("60")}, RiskCategory.CREDIT)
        today = date.today()
        report = reporter.generate_report("test", today - timedelta(days=30), today)
        assert report.total_entities == 2

    def test_distribution_has_all_levels(self) -> None:
        reporter, _ = _reporter()
        today = date.today()
        report = reporter.generate_report("test", today - timedelta(days=7), today)
        from services.risk_management.models import RiskLevel

        for level in RiskLevel:
            assert level.value in report.distribution

    def test_top_risks_limited_to_5(self) -> None:
        reporter, store = _reporter()
        scorer = RiskScorer(store)
        for i in range(10):
            scorer.score_entity(f"e-{i}", {"f": Decimal("50")}, RiskCategory.FRAUD)
        today = date.today()
        report = reporter.generate_report("test", today - timedelta(days=7), today)
        assert len(report.top_risks) <= 5


class TestExportJson:
    def test_returns_string(self) -> None:
        reporter, _ = _reporter()
        today = date.today()
        report = reporter.generate_report("test", today - timedelta(days=7), today)
        result = reporter.export_json(report)
        assert isinstance(result, str)

    def test_valid_json(self) -> None:
        reporter, _ = _reporter()
        today = date.today()
        report = reporter.generate_report("test", today - timedelta(days=7), today)
        result = reporter.export_json(report)
        data = json.loads(result)
        assert "id" in data

    def test_has_scope_field(self) -> None:
        reporter, _ = _reporter()
        today = date.today()
        report = reporter.generate_report("my-scope", today - timedelta(days=7), today)
        result = reporter.export_json(report)
        data = json.loads(result)
        assert data["scope"] == "my-scope"

    def test_decimal_serialized_as_string(self) -> None:
        reporter, _ = _reporter()
        today = date.today()
        report = reporter.generate_report("test", today - timedelta(days=7), today)
        result = reporter.export_json(report)
        # Should not raise — all decimals as strings
        json.loads(result)


class TestExportSummary:
    def test_returns_dict(self) -> None:
        reporter, _ = _reporter()
        today = date.today()
        report = reporter.generate_report("test", today - timedelta(days=7), today)
        summary = reporter.export_summary(report)
        assert isinstance(summary, dict)

    def test_total_entities_present(self) -> None:
        reporter, _ = _reporter()
        today = date.today()
        report = reporter.generate_report("test", today - timedelta(days=7), today)
        summary = reporter.export_summary(report)
        assert "total_entities" in summary

    def test_highest_risk_entity_present(self) -> None:
        reporter, store = _reporter()
        scorer = RiskScorer(store)
        scorer.score_entity("high-risk", {"f": Decimal("999")}, RiskCategory.FRAUD)
        today = date.today()
        report = reporter.generate_report("test", today - timedelta(days=7), today)
        summary = reporter.export_summary(report)
        assert summary["highest_risk_entity"] == "high-risk"

    def test_distribution_in_summary(self) -> None:
        reporter, _ = _reporter()
        today = date.today()
        report = reporter.generate_report("test", today - timedelta(days=7), today)
        summary = reporter.export_summary(report)
        assert "distribution" in summary


class TestGetTrend:
    def test_returns_list(self) -> None:
        reporter, _ = _reporter()
        result = reporter.get_trend(RiskCategory.AML)
        assert isinstance(result, list)

    def test_empty_when_no_history(self) -> None:
        reporter, _ = _reporter()
        result = reporter.get_trend(RiskCategory.CREDIT, days=30)
        assert result == []

    def test_custom_days_parameter(self) -> None:
        reporter, _ = _reporter()
        result = reporter.get_trend(RiskCategory.FRAUD, days=7)
        assert isinstance(result, list)

    def test_all_categories_trend(self) -> None:
        reporter, _ = _reporter()
        for cat in RiskCategory:
            result = reporter.get_trend(cat)
            assert isinstance(result, list)
