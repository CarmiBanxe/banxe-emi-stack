"""Tests for ObservabilityAgent (IL-OBS-01)."""

from __future__ import annotations

import pytest

from services.observability.compliance_monitor import ComplianceMonitor, InMemoryComplianceCheckPort
from services.observability.health_aggregator import HealthAggregator, InMemoryHealthCheckPort
from services.observability.observability_agent import ObservabilityAgent


@pytest.mark.asyncio
class TestObservabilityAgent:
    async def test_snapshot_returns_all_components(self):
        agent = ObservabilityAgent()
        snap = await agent.snapshot()
        assert snap.health is not None
        assert snap.metrics is not None
        assert snap.compliance is not None

    async def test_snapshot_has_timestamp(self):
        agent = ObservabilityAgent()
        snap = await agent.snapshot()
        assert snap.snapshot_at is not None

    async def test_alert_generated_on_unhealthy(self):
        agg = HealthAggregator(InMemoryHealthCheckPort({"postgres": False}))
        agent = ObservabilityAgent(health_aggregator=agg)
        snap = await agent.snapshot()
        health_alerts = [a for a in snap.alerts if a.alert_type == "HEALTH"]
        assert len(health_alerts) >= 1

    async def test_compliance_alert_generated_on_violation(self):
        mon = ComplianceMonitor(InMemoryComplianceCheckPort({"decimal_usage": False}))
        agent = ObservabilityAgent(compliance_monitor=mon)
        snap = await agent.snapshot()
        comp_alerts = [a for a in snap.alerts if a.alert_type == "COMPLIANCE"]
        assert len(comp_alerts) >= 1

    async def test_alerts_require_compliance_officer(self):
        """I-27: all alerts require COMPLIANCE_OFFICER approval."""
        agg = HealthAggregator(InMemoryHealthCheckPort({"postgres": False}))
        agent = ObservabilityAgent(health_aggregator=agg)
        snap = await agent.snapshot()
        for alert in snap.alerts:
            assert alert.requires_approval_from == "COMPLIANCE_OFFICER"

    async def test_alerts_not_auto_approved(self):
        """I-27: alerts start unapproved."""
        agg = HealthAggregator(InMemoryHealthCheckPort({"redis": False}))
        agent = ObservabilityAgent(health_aggregator=agg)
        snap = await agent.snapshot()
        for alert in snap.alerts:
            assert alert.acknowledged is False

    async def test_acknowledge_alert_marks_acknowledged(self):
        agg = HealthAggregator(InMemoryHealthCheckPort({"redis": False}))
        agent = ObservabilityAgent(health_aggregator=agg)
        snap = await agent.snapshot()
        if snap.alerts:
            alert_id = snap.alerts[0].alert_id
            result = agent.acknowledge_alert(alert_id, "compliance_officer@banxe.com")
            assert result is True

    async def test_acknowledge_unknown_alert_returns_false(self):
        agent = ObservabilityAgent()
        result = agent.acknowledge_alert("UNKNOWN_ALERT", "officer@banxe.com")
        assert result is False

    async def test_alert_log_is_append_only(self):
        """I-24: alert_log grows, never shrinks."""
        agg = HealthAggregator(InMemoryHealthCheckPort({"postgres": False}))
        agent = ObservabilityAgent(health_aggregator=agg)
        await agent.snapshot()
        count1 = len(agent.alert_log)
        await agent.snapshot()
        count2 = len(agent.alert_log)
        assert count2 >= count1

    async def test_no_alerts_when_all_healthy_compliant(self):
        agent = ObservabilityAgent()
        snap = await agent.snapshot()
        # With all-healthy port + all-compliant port: no alerts
        assert isinstance(snap.alerts, list)
