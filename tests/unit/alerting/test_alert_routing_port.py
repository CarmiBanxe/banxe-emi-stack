"""ADR-033 Step 1: 6 unit tests for AlertRoutingPort + Alert + InMemory adapter."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from services.alerting.alert_port import Alert, AlertCategory, AlertSeverity
from services.alerting.in_memory_adapter import InMemoryAlertAdapter


def _make_alert() -> Alert:
    return Alert(
        category=AlertCategory.AUTH_BRUTE_FORCE,
        severity=AlertSeverity.CRITICAL,
        title="brute-force detected",
        body="10 failed logins from 1.2.3.4",
    )


@pytest.mark.asyncio
async def test_send_alert_success() -> None:
    adapter = InMemoryAlertAdapter(healthy=True)
    alert = _make_alert()
    ok = await adapter.send_alert(alert)
    assert ok is True
    assert adapter.alerts == [alert]


@pytest.mark.asyncio
async def test_send_alert_failure_unhealthy() -> None:
    adapter = InMemoryAlertAdapter(healthy=False)
    ok = await adapter.send_alert(_make_alert())
    assert ok is False
    assert adapter.alerts == []


@pytest.mark.asyncio
async def test_health_check_healthy() -> None:
    adapter = InMemoryAlertAdapter(healthy=True)
    assert await adapter.health_check() is True


@pytest.mark.asyncio
async def test_health_check_unhealthy() -> None:
    adapter = InMemoryAlertAdapter(healthy=False)
    assert await adapter.health_check() is False


def test_alert_is_frozen() -> None:
    alert = _make_alert()
    with pytest.raises(FrozenInstanceError):
        alert.title = "mutated"  # type: ignore[misc]


def test_alert_severity_and_category_enums() -> None:
    assert AlertSeverity.INFO.value == "INFO"
    assert AlertSeverity.WARNING.value == "WARNING"
    assert AlertSeverity.CRITICAL.value == "CRITICAL"
    assert AlertCategory.AUTH_BRUTE_FORCE.value == "AUTH_BRUTE_FORCE"
    assert AlertCategory.CLIENT_SECRET_EXPOSURE.value == "CLIENT_SECRET_EXPOSURE"
    assert AlertCategory.TOKEN_REPLAY.value == "TOKEN_REPLAY"
    assert AlertCategory.ADMIN_USER_DELETE.value == "ADMIN_USER_DELETE"
    assert AlertCategory.ADMIN_PASSWORD_RESET.value == "ADMIN_PASSWORD_RESET"
    assert AlertCategory.SAFEGUARDING_SHORTFALL.value == "SAFEGUARDING_SHORTFALL"
    assert AlertCategory.GENERIC.value == "GENERIC"
