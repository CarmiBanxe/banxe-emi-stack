"""Tests for HealthAggregator (IL-OBS-01)."""

from __future__ import annotations

import pytest

from services.observability.health_aggregator import (
    HealthAggregator,
    InMemoryHealthCheckPort,
    ServiceStatus,
)


@pytest.mark.asyncio
class TestHealthAggregatorAllHealthy:
    async def test_all_healthy_returns_healthy(self):
        agg = HealthAggregator(InMemoryHealthCheckPort())
        report = await agg.check_all()
        assert report.overall_status == ServiceStatus.HEALTHY

    async def test_all_healthy_count(self):
        agg = HealthAggregator(InMemoryHealthCheckPort())
        report = await agg.check_all()
        assert report.healthy_count == len(HealthAggregator.SERVICES)

    async def test_unhealthy_count_zero_when_all_healthy(self):
        agg = HealthAggregator(InMemoryHealthCheckPort())
        report = await agg.check_all()
        assert report.unhealthy_count == 0

    async def test_postgres_down_returns_unhealthy(self):
        agg = HealthAggregator(InMemoryHealthCheckPort({"postgres": False}))
        report = await agg.check_all()
        assert report.overall_status == ServiceStatus.UNHEALTHY

    async def test_redis_down_returns_unhealthy(self):
        agg = HealthAggregator(InMemoryHealthCheckPort({"redis": False}))
        report = await agg.check_all()
        assert report.overall_status == ServiceStatus.UNHEALTHY

    async def test_check_all_returns_all_services(self):
        agg = HealthAggregator(InMemoryHealthCheckPort())
        report = await agg.check_all()
        service_names = {s.service for s in report.services}
        assert "postgres" in service_names
        assert "clickhouse" in service_names
        assert "redis" in service_names
        assert "frankfurter" in service_names

    async def test_health_log_append_only(self):
        """I-24: health log grows with each check_all call."""
        agg = HealthAggregator(InMemoryHealthCheckPort())
        await agg.check_all()
        await agg.check_all()
        assert len(agg.health_log) == 2

    async def test_check_service_known_healthy(self):
        agg = HealthAggregator(InMemoryHealthCheckPort())
        result = await agg.check_service("postgres")
        assert result.status == ServiceStatus.HEALTHY

    async def test_check_service_known_unhealthy(self):
        agg = HealthAggregator(InMemoryHealthCheckPort({"clickhouse": False}))
        result = await agg.check_service("clickhouse")
        assert result.status == ServiceStatus.UNHEALTHY

    async def test_check_service_unknown_returns_unhealthy(self):
        agg = HealthAggregator(InMemoryHealthCheckPort())
        result = await agg.check_service("nonexistent_service")
        assert result.status == ServiceStatus.UNHEALTHY

    async def test_report_has_checked_at(self):
        agg = HealthAggregator(InMemoryHealthCheckPort())
        report = await agg.check_all()
        assert report.checked_at is not None

    async def test_service_health_has_message(self):
        agg = HealthAggregator(InMemoryHealthCheckPort())
        report = await agg.check_all()
        for s in report.services:
            assert s.message is not None


@pytest.mark.asyncio
class TestHealthAggregatorPartialFailure:
    async def test_one_unhealthy_sets_overall_unhealthy(self):
        overrides = {"frankfurter": False}
        agg = HealthAggregator(InMemoryHealthCheckPort(overrides))
        report = await agg.check_all()
        assert report.overall_status == ServiceStatus.UNHEALTHY
        assert report.unhealthy_count == 1

    async def test_all_unhealthy(self):
        overrides = {s: False for s in HealthAggregator.SERVICES}
        agg = HealthAggregator(InMemoryHealthCheckPort(overrides))
        report = await agg.check_all()
        assert report.unhealthy_count == len(HealthAggregator.SERVICES)
