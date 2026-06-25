"""Tests for MetricsCollector (IL-OBS-01)."""

from __future__ import annotations

from decimal import Decimal

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

    def test_bt008_push_to_grafana_does_not_raise(self):
        """BT-008 resolved: push_to_grafana logs intent without raising."""
        mc = MetricsCollector()
        snap = mc.collect()
        mc.push_to_grafana(snap)  # must not raise

    def test_bt008_push_appends_to_grafana_log(self):
        """BT-008: I-24 — grafana push intent is logged."""
        mc = MetricsCollector()
        snap = mc.collect()
        mc.push_to_grafana(snap)
        assert len(mc.grafana_log) == 1

    def test_bt008_push_log_delivered_false(self):
        """BT-008: delivered=False until P1 Grafana adapter is wired."""
        mc = MetricsCollector()
        snap = mc.collect()
        mc.push_to_grafana(snap)
        assert mc.grafana_log[0]["delivered"] is False

    def test_snapshot_has_collected_at(self):
        mc = MetricsCollector()
        snap = mc.collect()
        assert snap.collected_at is not None

    def test_coverage_pct_reasonable(self):
        mc = MetricsCollector()
        snap = mc.collect()
        assert Decimal("0") <= snap.coverage_pct <= Decimal("100")
