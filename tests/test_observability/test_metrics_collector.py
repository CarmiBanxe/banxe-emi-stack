"""Tests for MetricsCollector (IL-OBS-01)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.observability.metrics_collector import MetricsCollector, MetricsSnapshot


class TestMetricsCollector:
    def test_collect_returns_snapshot(self):
        mc = MetricsCollector()
        snap = mc.collect()
        assert isinstance(snap, MetricsSnapshot)

    def test_coverage_pct_is_decimal(self):
        """I-01: coverage_pct must be Decimal."""
        mc = MetricsCollector()
        snap = mc.collect()
        assert isinstance(snap.coverage_pct, Decimal)
        assert not isinstance(snap.coverage_pct, float)

    def test_test_count_above_gate(self):
        """Gate G0.5: test count must exceed 8000."""
        mc = MetricsCollector()
        snap = mc.collect()
        assert snap.test_count >= 8000

    def test_endpoint_count_positive(self):
        mc = MetricsCollector()
        snap = mc.collect()
        assert snap.endpoint_count > 0

    def test_mcp_tool_count_positive(self):
        mc = MetricsCollector()
        snap = mc.collect()
        assert snap.mcp_tool_count > 0

    def test_passport_count_positive(self):
        mc = MetricsCollector()
        snap = mc.collect()
        assert snap.passport_count > 0

    def test_overrides_applied(self):
        mc = MetricsCollector(overrides={"test_count": 9999})
        snap = mc.collect()
        assert snap.test_count == 9999

    def test_push_to_grafana_raises_not_implemented(self):
        """BT-008: Grafana push is a stub."""
        mc = MetricsCollector()
        snap = mc.collect()
        with pytest.raises(NotImplementedError, match="BT-008"):
            mc.push_to_grafana(snap)

    def test_snapshot_has_collected_at(self):
        mc = MetricsCollector()
        snap = mc.collect()
        assert snap.collected_at is not None

    def test_coverage_pct_reasonable(self):
        mc = MetricsCollector()
        snap = mc.collect()
        assert Decimal("0") <= snap.coverage_pct <= Decimal("100")
