"""Smoke tests for ADR-033 Step 3: alert routing operational readiness."""

from __future__ import annotations

from pathlib import Path
import py_compile

import pytest

from services.alerting.alert_port import (
    Alert,
    AlertCategory,
    AlertRoutingPort,
    AlertSeverity,
)
from services.alerting.di import AlertConfig, get_alert_adapter
from services.alerting.in_memory_adapter import InMemoryAlertAdapter


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("ALERT_ENABLED", "ALERT_N8N_WEBHOOK_URL", "ALERT_TIMEOUT"):
        monkeypatch.delenv(key, raising=False)


def test_alert_config_loads_from_env(clean_env: None) -> None:
    config = AlertConfig.from_env()
    assert isinstance(config, AlertConfig)
    assert isinstance(config.webhook_url, str) and config.webhook_url
    assert isinstance(config.timeout, float)
    assert isinstance(config.enabled, bool)


def test_get_adapter_returns_port_instance(clean_env: None) -> None:
    adapter = get_alert_adapter()
    assert isinstance(adapter, AlertRoutingPort)


@pytest.mark.asyncio
async def test_in_memory_adapter_send_and_retrieve() -> None:
    adapter = InMemoryAlertAdapter(healthy=True)
    alert = Alert(
        category=AlertCategory.GENERIC,
        severity=AlertSeverity.INFO,
        title="smoke",
        body="smoke body",
    )
    ok = await adapter.send_alert(alert)
    assert ok is True
    assert adapter.alerts == [alert]


def test_alert_script_exists_and_executable() -> None:
    script = Path(__file__).resolve().parents[2] / "scripts" / "alert-routing-check.py"
    assert script.exists(), f"script not found: {script}"
    py_compile.compile(str(script), doraise=True)
