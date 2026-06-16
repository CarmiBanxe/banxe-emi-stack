"""ADR-033 Step 2: 5 integration tests for AlertConfig + get_alert_adapter."""

from __future__ import annotations

import pytest

from services.alerting.alert_port import AlertRoutingPort
from services.alerting.di import AlertConfig, get_alert_adapter
from services.alerting.in_memory_adapter import InMemoryAlertAdapter
from services.alerting.n8n_telegram_adapter import N8nTelegramAlertAdapter

_DEFAULT_WEBHOOK_URL = "http://192.168.0.72:5678/webhook/kc-events"


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("ALERT_ENABLED", "ALERT_N8N_WEBHOOK_URL", "ALERT_TIMEOUT"):
        monkeypatch.delenv(key, raising=False)


def test_default_config_disabled(clean_env: None) -> None:
    config = AlertConfig.from_env()
    assert config.enabled is False
    assert config.webhook_url == _DEFAULT_WEBHOOK_URL
    assert config.timeout == 10.0


def test_config_from_env_enabled(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALERT_ENABLED", "true")
    config = AlertConfig.from_env()
    assert config.enabled is True
    assert config.webhook_url == _DEFAULT_WEBHOOK_URL


def test_get_adapter_disabled_returns_in_memory(clean_env: None) -> None:
    config = AlertConfig(webhook_url=_DEFAULT_WEBHOOK_URL, enabled=False)
    adapter: AlertRoutingPort = get_alert_adapter(config)
    assert isinstance(adapter, InMemoryAlertAdapter)


def test_get_adapter_enabled_returns_n8n(clean_env: None) -> None:
    config = AlertConfig(webhook_url=_DEFAULT_WEBHOOK_URL, enabled=True)
    adapter: AlertRoutingPort = get_alert_adapter(config)
    assert isinstance(adapter, N8nTelegramAlertAdapter)


def test_config_custom_values(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    custom_url = "http://10.0.0.5:5678/webhook/custom-alerts"
    monkeypatch.setenv("ALERT_N8N_WEBHOOK_URL", custom_url)
    monkeypatch.setenv("ALERT_TIMEOUT", "25.5")
    config = AlertConfig.from_env()
    assert config.webhook_url == custom_url
    assert config.timeout == 25.5
