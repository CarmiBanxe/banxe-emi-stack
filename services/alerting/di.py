"""ADR-033 Step 2: DI wiring for AlertRoutingPort.

AlertConfig.from_env() reads ALERT_ENABLED / ALERT_N8N_WEBHOOK_URL /
ALERT_TIMEOUT. get_alert_adapter() returns the in-memory test double when
disabled (safe default) and the real n8n+Telegram adapter when enabled.
"""

from __future__ import annotations

from dataclasses import dataclass
import os

from .alert_port import AlertRoutingPort
from .in_memory_adapter import InMemoryAlertAdapter
from .n8n_telegram_adapter import N8nTelegramAlertAdapter

_DEFAULT_WEBHOOK_URL = "http://192.168.0.72:5678/webhook/kc-events"
_DEFAULT_TIMEOUT = 10.0


def _env_bool(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class AlertConfig:
    webhook_url: str
    timeout: float = _DEFAULT_TIMEOUT
    enabled: bool = False

    @classmethod
    def from_env(cls) -> AlertConfig:
        webhook_url = os.environ.get("ALERT_N8N_WEBHOOK_URL", _DEFAULT_WEBHOOK_URL)
        raw_timeout = os.environ.get("ALERT_TIMEOUT", str(_DEFAULT_TIMEOUT))
        timeout = float(raw_timeout)  # nosemgrep: banxe-float-money — seconds, not money
        enabled = _env_bool(os.environ.get("ALERT_ENABLED"))
        return cls(webhook_url=webhook_url, timeout=timeout, enabled=enabled)


def get_alert_adapter(config: AlertConfig | None = None) -> AlertRoutingPort:
    if config is None:
        config = AlertConfig.from_env()
    if not config.enabled:
        return InMemoryAlertAdapter()
    return N8nTelegramAlertAdapter(
        webhook_url=config.webhook_url,
        timeout=config.timeout,
    )
