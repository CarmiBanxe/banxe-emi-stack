"""
tests/test_reporting_analytics/test_data_aggregator.py
IL-RAP-01 | Phase 38 | banxe-emi-stack — 16 tests
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from services.reporting_analytics.data_aggregator import DataAggregator
from services.reporting_analytics.models import (
    AggregationType,
    DataSource,
    ScheduleFrequency,
)

_NOW = datetime.now(UTC)
_PAST = datetime(2026, 1, 1, tzinfo=UTC)


def _agg() -> DataAggregator:
    return DataAggregator()


class TestAggregate:
    def test_sum_returns_decimal(self) -> None:
        agg = _agg()
        result = agg.aggregate(DataSource.TRANSACTIONS, AggregationType.SUM, {}, _PAST, _NOW)
        assert isinstance(result, Decimal)

    def test_count_returns_one(self) -> None:
        agg = _agg()
        result = agg.aggregate(DataSource.AML_ALERTS, AggregationType.COUNT, {}, _PAST, _NOW)
        assert result == Decimal("1")

    def test_average_returns_zero(self) -> None:
        agg = _agg()
        result = agg.aggregate(DataSource.RISK_SCORES, AggregationType.AVERAGE, {}, _PAST, _NOW)
        assert result == Decimal("0")

    def test_min_returns_decimal(self) -> None:
        agg = _agg()
        result = agg.aggregate(DataSource.TREASURY, AggregationType.MIN, {}, _PAST, _NOW)
        assert isinstance(result, Decimal)

    def test_max_returns_decimal(self) -> None:
        agg = _agg()
        result = agg.aggregate(DataSource.CUSTOMER_DATA, AggregationType.MAX, {}, _PAST, _NOW)
        assert isinstance(result, Decimal)

    def test_percentile_95_returns_decimal(self) -> None:
        agg = _agg()
        result = agg.aggregate(
            DataSource.COMPLIANCE_EVENTS, AggregationType.PERCENTILE_95, {}, _PAST, _NOW
        )
        assert isinstance(result, Decimal)


class TestMultiSourceAggregate:
    def test_returns_dict(self) -> None:
        agg = _agg()
        result = agg.multi_source_aggregate(
            [DataSource.TRANSACTIONS, DataSource.AML_ALERTS],
            AggregationType.SUM,
            {},
        )
        assert isinstance(result, dict)

    def test_all_sources_present(self) -> None:
        agg = _agg()
        sources = [DataSource.TRANSACTIONS, DataSource.RISK_SCORES]
        result = agg.multi_source_aggregate(sources, AggregationType.COUNT, {})
        for s in sources:
            assert s.value in result

    def test_values_are_decimal(self) -> None:
        agg = _agg()
        result = agg.multi_source_aggregate([DataSource.TREASURY], AggregationType.SUM, {})
        for v in result.values():
            assert isinstance(v, Decimal)

    def test_empty_sources_returns_empty(self) -> None:
        agg = _agg()
        result = agg.multi_source_aggregate([], AggregationType.SUM, {})
        assert result == {}


class TestTimeSeriesRollup:
    def test_returns_list(self) -> None:
        agg = _agg()
        result = agg.time_series_rollup(
            DataSource.TRANSACTIONS, ScheduleFrequency.DAILY, _PAST, _NOW
        )
        assert isinstance(result, list)

    def test_stub_returns_empty(self) -> None:
        agg = _agg()
        result = agg.time_series_rollup(
            DataSource.AML_ALERTS, ScheduleFrequency.WEEKLY, _PAST, _NOW
        )
        assert result == []


class TestGetAvailableSources:
    def test_returns_list(self) -> None:
        agg = _agg()
        sources = agg.get_available_sources()
        assert isinstance(sources, list)

    def test_contains_all_sources(self) -> None:
        agg = _agg()
        sources = agg.get_available_sources()
        for ds in DataSource:
            assert ds in sources

    def test_returns_data_source_instances(self) -> None:
        agg = _agg()
        sources = agg.get_available_sources()
        for s in sources:
            assert isinstance(s, DataSource)

    def test_non_empty(self) -> None:
        agg = _agg()
        sources = agg.get_available_sources()
        assert len(sources) > 0
