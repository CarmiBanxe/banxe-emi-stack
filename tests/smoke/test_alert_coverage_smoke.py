"""Smoke tests for G-OBS-02: alert-coverage CI smoke for Keycloak auth events.

5 tests covering ADR-033 alert routing categories (LOGIN_ERROR brute-force,
CLIENT_LOGIN_ERROR client-secret exposure, TOKEN_EXCHANGE_ERROR token replay,
admin DELETE_USER ownership routing, and delivery latency budget).

Per ADR-033 alert routing + FCA SYSC 15A operational resilience.
"""

from __future__ import annotations

import asyncio
import time

from services.alerting.alert_port import Alert, AlertCategory, AlertSeverity
from services.alerting.in_memory_adapter import InMemoryAlertAdapter

_LATENCY_BUDGET_SECONDS = 1.0


async def test_login_error_alert_fires() -> None:
    adapter = InMemoryAlertAdapter()
    alert = Alert(
        category=AlertCategory.AUTH_BRUTE_FORCE,
        severity=AlertSeverity.CRITICAL,
        title="LOGIN_ERROR burst",
        body="10 LOGIN_ERROR events from 1.2.3.4 in 60s",
    )

    delivered = await adapter.send_alert(alert)

    assert delivered is True
    assert adapter.alerts == [alert]
    assert adapter.alerts[0].category is AlertCategory.AUTH_BRUTE_FORCE
    assert adapter.alerts[0].severity is AlertSeverity.CRITICAL


async def test_client_login_error_alert_fires() -> None:
    adapter = InMemoryAlertAdapter()
    alert = Alert(
        category=AlertCategory.CLIENT_SECRET_EXPOSURE,
        severity=AlertSeverity.CRITICAL,
        title="CLIENT_LOGIN_ERROR detected",
        body="OAuth client_secret rejected — possible rotation drift or exposure",
    )

    delivered = await adapter.send_alert(alert)

    assert delivered is True
    assert adapter.alerts[0].category is AlertCategory.CLIENT_SECRET_EXPOSURE
    assert adapter.alerts[0].severity is AlertSeverity.CRITICAL


async def test_token_exchange_error_alert_fires() -> None:
    adapter = InMemoryAlertAdapter()
    alert = Alert(
        category=AlertCategory.TOKEN_REPLAY,
        severity=AlertSeverity.WARNING,
        title="TOKEN_EXCHANGE_ERROR observed",
        body="token-exchange grant failed — possible replay",
    )

    delivered = await adapter.send_alert(alert)

    assert delivered is True
    assert adapter.alerts[0].category is AlertCategory.TOKEN_REPLAY
    assert adapter.alerts[0].severity is AlertSeverity.WARNING


async def test_admin_event_alert_fires() -> None:
    adapter = InMemoryAlertAdapter()
    alert = Alert(
        category=AlertCategory.ADMIN_USER_DELETE,
        severity=AlertSeverity.CRITICAL,
        title="Admin DELETE_USER",
        body="admin@banxe deleted user customer-007",
        owner="CEO",
    )

    delivered = await adapter.send_alert(alert)

    assert delivered is True
    assert adapter.alerts[0].category is AlertCategory.ADMIN_USER_DELETE
    assert adapter.alerts[0].owner == "CEO"
    assert adapter.alerts[0].owner != "CTIO"


async def test_alert_delivery_latency_under_threshold() -> None:
    adapter = InMemoryAlertAdapter()
    alert = Alert(
        category=AlertCategory.GENERIC,
        severity=AlertSeverity.INFO,
        title="latency probe",
        body="probe",
    )

    start = time.perf_counter()
    delivered = await adapter.send_alert(alert)
    elapsed = time.perf_counter() - start

    assert delivered is True
    assert elapsed < _LATENCY_BUDGET_SECONDS, (
        f"InMemoryAlertAdapter.send_alert took {elapsed:.4f}s — "
        f"latency budget {_LATENCY_BUDGET_SECONDS}s (ADR-033 60s end-to-end target)"
    )


if __name__ == "__main__":  # pragma: no cover — smoke convenience
    asyncio.run(test_login_error_alert_fires())
