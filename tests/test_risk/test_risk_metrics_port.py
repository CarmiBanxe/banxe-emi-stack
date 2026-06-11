"""InMemoryRiskMetricsPort unit tests — 100% coverage over services/risk/risk_metrics_port.py.

Validates the InMemoryRiskMetricsPort implementation: happy-path reads for all 4 methods,
failure paths (fail_on_call=True), custom seed data injection, value type invariants
(I-01: Decimal for total_gbp), and dashboard consistency with individual reads.

asyncio_mode = "auto" (pyproject.toml): every ``async def test_*`` is auto-collected
without @pytest.mark.asyncio.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.risk.risk_metrics_port import (
    AggregateExposure,
    ConsumerDutySignal,
    InMemoryRiskMetricsPort,
    MonitoringCounters,
    RiskDashboard,
    RiskMetricsPortError,
)

# ---------------------------------------------------------------------------
# Happy path — default seed data
# ---------------------------------------------------------------------------


async def test_get_aggregate_exposure_returns_correct_type() -> None:
    """Default seed returns AggregateExposure with Decimal total_gbp (I-01)."""
    port = InMemoryRiskMetricsPort()
    result = await port.get_aggregate_exposure()

    assert isinstance(result, AggregateExposure)
    assert isinstance(result.total_gbp, Decimal)
    assert result.total_gbp > Decimal("0")
    assert isinstance(result.as_of, str)


async def test_get_monitoring_counters_returns_correct_type() -> None:
    """Default seed returns MonitoringCounters with int alert fields."""
    port = InMemoryRiskMetricsPort()
    result = await port.get_monitoring_counters()

    assert isinstance(result, MonitoringCounters)
    assert isinstance(result.fraud_alerts, int)
    assert isinstance(result.aml_alerts, int)
    assert isinstance(result.as_of, str)


async def test_get_consumer_duty_signals_returns_nonempty_list() -> None:
    """Default seed returns a non-empty list of ConsumerDutySignal."""
    port = InMemoryRiskMetricsPort()
    result = await port.get_consumer_duty_signals()

    assert isinstance(result, list)
    assert len(result) >= 1
    assert isinstance(result[0], ConsumerDutySignal)
    assert isinstance(result[0].metric, str)
    assert isinstance(result[0].outcome, str)


async def test_get_risk_dashboard_returns_correct_type() -> None:
    """Default seed returns RiskDashboard aggregating all three metric categories."""
    port = InMemoryRiskMetricsPort()
    result = await port.get_risk_dashboard()

    assert isinstance(result, RiskDashboard)
    assert isinstance(result.aggregate, AggregateExposure)
    assert isinstance(result.counters, MonitoringCounters)
    assert isinstance(result.consumer_duty, list)
    assert isinstance(result.as_of, str)


# ---------------------------------------------------------------------------
# Custom seed data
# ---------------------------------------------------------------------------


async def test_custom_exposure_seed_returned_unchanged() -> None:
    """Custom AggregateExposure seed is returned exactly as injected."""
    custom = AggregateExposure(total_gbp=Decimal("5_000_000.00"), as_of="2026-01-01")
    port = InMemoryRiskMetricsPort(exposure=custom)
    result = await port.get_aggregate_exposure()
    assert result is custom


async def test_custom_counters_seed_returned_unchanged() -> None:
    """Custom MonitoringCounters seed is returned exactly as injected."""
    custom = MonitoringCounters(fraud_alerts=99, aml_alerts=42, as_of="2026-01-01")
    port = InMemoryRiskMetricsPort(counters=custom)
    result = await port.get_monitoring_counters()
    assert result is custom


async def test_custom_signals_seed_returned_as_copy() -> None:
    """Custom signals seed returns a list copy with the same elements (defensive copy)."""
    custom = [ConsumerDutySignal(metric="m1", outcome="OK", as_of="2026-01-01")]
    port = InMemoryRiskMetricsPort(signals=custom)
    result = await port.get_consumer_duty_signals()

    assert result == custom
    # Returned list is a copy, not the same object.
    assert result is not custom


async def test_empty_signals_seed_returns_empty_list() -> None:
    """Empty signals seed returns an empty list (not None)."""
    port = InMemoryRiskMetricsPort(signals=[])
    result = await port.get_consumer_duty_signals()
    assert result == []


# ---------------------------------------------------------------------------
# Failure paths (fail_on_call=True)
# ---------------------------------------------------------------------------


async def test_fail_on_get_aggregate_exposure() -> None:
    """fail_on_call=True raises RiskMetricsPortError on get_aggregate_exposure."""
    port = InMemoryRiskMetricsPort(fail_on_call=True)
    with pytest.raises(RiskMetricsPortError):
        await port.get_aggregate_exposure()


async def test_fail_on_get_monitoring_counters() -> None:
    """fail_on_call=True raises RiskMetricsPortError on get_monitoring_counters."""
    port = InMemoryRiskMetricsPort(fail_on_call=True)
    with pytest.raises(RiskMetricsPortError):
        await port.get_monitoring_counters()


async def test_fail_on_get_consumer_duty_signals() -> None:
    """fail_on_call=True raises RiskMetricsPortError on get_consumer_duty_signals."""
    port = InMemoryRiskMetricsPort(fail_on_call=True)
    with pytest.raises(RiskMetricsPortError):
        await port.get_consumer_duty_signals()


async def test_fail_on_get_risk_dashboard() -> None:
    """fail_on_call=True raises RiskMetricsPortError on get_risk_dashboard."""
    port = InMemoryRiskMetricsPort(fail_on_call=True)
    with pytest.raises(RiskMetricsPortError):
        await port.get_risk_dashboard()


# ---------------------------------------------------------------------------
# Dashboard consistency: same seed data appears in all legs
# ---------------------------------------------------------------------------


async def test_risk_dashboard_consistent_with_individual_reads() -> None:
    """RiskDashboard fields are consistent with the individual method return values."""
    custom_exposure = AggregateExposure(total_gbp=Decimal("2_500_000.00"), as_of="2026-06-11")
    custom_counters = MonitoringCounters(fraud_alerts=7, aml_alerts=2, as_of="2026-06-11")
    custom_signals = [
        ConsumerDutySignal(metric="complaints_rate", outcome="WITHIN_TOLERANCE", as_of="2026-06-11")
    ]

    port = InMemoryRiskMetricsPort(
        exposure=custom_exposure,
        counters=custom_counters,
        signals=custom_signals,
    )

    dashboard = await port.get_risk_dashboard()
    exposure = await port.get_aggregate_exposure()
    counters = await port.get_monitoring_counters()
    signals = await port.get_consumer_duty_signals()

    assert dashboard.aggregate == exposure
    assert dashboard.counters == counters
    assert dashboard.consumer_duty == signals
