"""
tests/test_reporting_analytics/test_dashboard_metrics.py
IL-RAP-01 | Phase 38 | banxe-emi-stack — 14 tests
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from services.reporting_analytics.dashboard_metrics import DashboardMetrics

_START = datetime(2026, 1, 1, tzinfo=UTC)
_END = datetime(2026, 3, 31, tzinfo=UTC)


def _metrics() -> DashboardMetrics:
    return DashboardMetrics()


class TestGetKpi:
    def test_returns_kpi_metric(self) -> None:
        m = _metrics()
        kpi = m.get_kpi("revenue", _START, _END)
        assert kpi.name == "revenue"

    def test_value_is_decimal(self) -> None:
        m = _metrics()
        kpi = m.get_kpi("revenue", _START, _END)
        assert isinstance(kpi.value, Decimal)

    def test_compliance_rate_is_100(self) -> None:
        m = _metrics()
        kpi = m.get_kpi("compliance_rate", _START, _END)
        assert kpi.value == Decimal("100")

    def test_unknown_kpi_returns_zero(self) -> None:
        m = _metrics()
        kpi = m.get_kpi("nonexistent_kpi", _START, _END)
        assert kpi.value == Decimal("0")

    def test_sparkline_is_list(self) -> None:
        m = _metrics()
        kpi = m.get_kpi("nps", _START, _END)
        assert isinstance(kpi.sparkline, list)


class TestGetAllKpis:
    def test_returns_list(self) -> None:
        m = _metrics()
        kpis = m.get_all_kpis(_START, _END)
        assert isinstance(kpis, list)

    def test_non_empty(self) -> None:
        m = _metrics()
        kpis = m.get_all_kpis(_START, _END)
        assert len(kpis) > 0

    def test_all_values_decimal(self) -> None:
        m = _metrics()
        for kpi in m.get_all_kpis(_START, _END):
            assert isinstance(kpi.value, Decimal)

    def test_includes_compliance_rate(self) -> None:
        m = _metrics()
        names = [k.name for k in m.get_all_kpis(_START, _END)]
        assert "compliance_rate" in names


class TestGetSparkline:
    def test_returns_list(self) -> None:
        m = _metrics()
        result = m.get_sparkline("revenue")
        assert isinstance(result, list)

    def test_default_7_values(self) -> None:
        m = _metrics()
        result = m.get_sparkline("revenue")
        assert len(result) == 7

    def test_custom_days(self) -> None:
        m = _metrics()
        result = m.get_sparkline("nps", days=14)
        assert len(result) == 14


class TestGetComplianceScore:
    def test_returns_decimal(self) -> None:
        m = _metrics()
        score = m.get_compliance_score()
        assert isinstance(score, Decimal)

    def test_is_100(self) -> None:
        m = _metrics()
        assert m.get_compliance_score() == Decimal("100")
