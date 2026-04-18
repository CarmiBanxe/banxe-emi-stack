"""
services/reporting_analytics/dashboard_metrics.py
IL-RAP-01 | Phase 38 | banxe-emi-stack

Dashboard Metrics — KPI computation, sparklines, compliance score.
I-01: All values as Decimal (never float).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from services.reporting_analytics.models import KPIMetric

_ZERO = Decimal("0")
_HUNDRED = Decimal("100")

_STUB_KPIS: dict[str, tuple[Decimal, str]] = {
    "revenue": (_ZERO, "GBP"),
    "volume": (_ZERO, "GBP"),
    "compliance_rate": (_HUNDRED, "%"),
    "nps": (_ZERO, "score"),
}


class DashboardMetrics:
    """Provides KPI metrics and compliance scores for dashboards."""

    def get_kpi(self, name: str, period_start: datetime, period_end: datetime) -> KPIMetric:
        """Return a KPI metric by name (stub: zero/100 values)."""
        value, unit = _STUB_KPIS.get(name, (_ZERO, ""))
        return KPIMetric(
            name=name,
            value=value,
            unit=unit,
            period_start=period_start,
            period_end=period_end,
            trend="STABLE",
            sparkline=self.get_sparkline(name),
        )

    def get_all_kpis(self, period_start: datetime, period_end: datetime) -> list[KPIMetric]:
        """Return all available KPI metrics."""
        return [self.get_kpi(name, period_start, period_end) for name in _STUB_KPIS]

    def get_sparkline(self, name: str, days: int = 7) -> list[Decimal]:
        """Return N Decimal values for sparkline (stub: zeros)."""
        return [_ZERO] * days

    def get_compliance_score(self) -> Decimal:
        """Return compliance rate as 0-100 score (I-01)."""
        return _HUNDRED
