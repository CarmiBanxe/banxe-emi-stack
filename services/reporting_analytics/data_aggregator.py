"""
services/reporting_analytics/data_aggregator.py
IL-RAP-01 | Phase 38 | banxe-emi-stack

Data Aggregator — aggregates data from multiple sources for reporting.
I-01: All values as Decimal (never float).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from services.reporting_analytics.models import (
    AggregationType,
    DataSource,
    ScheduleFrequency,
)

_ZERO = Decimal("0")
_ONE = Decimal("1")
_HUNDRED = Decimal("100")


class DataAggregator:
    """Aggregates data from multiple sources for analytics and reporting."""

    def aggregate(
        self,
        source: DataSource,
        aggregation: AggregationType,
        filters: dict,
        period_start: datetime,
        period_end: datetime,
    ) -> Decimal:
        """Aggregate a single data source for the given period (stub)."""
        match aggregation:
            case AggregationType.SUM:
                return _ZERO
            case AggregationType.AVERAGE:
                return _ZERO
            case AggregationType.COUNT:
                return _ONE
            case AggregationType.MIN:
                return _ZERO
            case AggregationType.MAX:
                return _ZERO
            case AggregationType.PERCENTILE_95:
                return _ZERO
            case _:
                return _ZERO

    def multi_source_aggregate(
        self,
        sources: list[DataSource],
        aggregation: AggregationType,
        filters: dict,
    ) -> dict[str, Decimal]:
        """Aggregate multiple sources simultaneously."""
        now = datetime.now()
        return {
            source.value: self.aggregate(source, aggregation, filters, now, now)
            for source in sources
        }

    def time_series_rollup(
        self,
        source: DataSource,
        frequency: ScheduleFrequency,
        period_start: datetime,
        period_end: datetime,
    ) -> list[dict]:
        """Return [{period, value: Decimal}] time series (stub: empty list)."""
        return []

    def get_available_sources(self) -> list[DataSource]:
        """Return all available data sources."""
        return list(DataSource)
