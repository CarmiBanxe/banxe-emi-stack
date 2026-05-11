"""
test_di_wiring.py — DI-resolution tests for WebhookReliabilityPort (ADR-034 Step 2).

Verifies api.deps.get_webhook_reliability_port() resolves the dev/test binding
to InMemoryWebhookAdapter with the documented env-var-driven configuration.

The provider is @lru_cache(maxsize=1); each test calls cache_clear() and uses
monkeypatch to vary env vars, so resolution is deterministic and isolated.
"""

from __future__ import annotations

import pytest

from api.deps import get_webhook_reliability_port
from services.webhooks.in_memory_adapter import (
    DEFAULT_BACKOFF_SCHEDULE,
    DEFAULT_MAX_ATTEMPTS,
    InMemoryWebhookAdapter,
)


@pytest.fixture(autouse=True)
def _clear_di_cache_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure each test sees a fresh provider resolution under known env."""
    monkeypatch.delenv("WEBHOOK_RELIABILITY_ADAPTER", raising=False)
    monkeypatch.delenv("WEBHOOK_MAX_ATTEMPTS", raising=False)
    monkeypatch.delenv("WEBHOOK_BACKOFF_SECONDS", raising=False)
    get_webhook_reliability_port.cache_clear()
    yield
    get_webhook_reliability_port.cache_clear()


def test_di_resolves_webhook_reliability_port_to_in_memory_adapter() -> None:
    port = get_webhook_reliability_port()
    assert isinstance(port, InMemoryWebhookAdapter)
    # Structural Port conformance — method surface per ADR-034 Step 1.
    # (Protocol is not @runtime_checkable by design; check by method names.)
    for method in ("enqueue", "mark_delivered", "mark_failed", "next_due"):
        assert callable(getattr(port, method)), f"port missing {method}"


def test_di_adapter_uses_default_backoff_schedule_from_config() -> None:
    port = get_webhook_reliability_port()
    assert port._backoff == DEFAULT_BACKOFF_SCHEDULE  # type: ignore[attr-defined]
    assert port._backoff == (1.0, 10.0, 60.0)  # type: ignore[attr-defined]


def test_di_adapter_backoff_schedule_overridable_via_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WEBHOOK_BACKOFF_SECONDS", "2.5, 7.0, 30.0, 120.0")
    get_webhook_reliability_port.cache_clear()
    port = get_webhook_reliability_port()
    assert port._backoff == (2.5, 7.0, 30.0, 120.0)  # type: ignore[attr-defined]


def test_di_adapter_max_attempts_configurable_via_di(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Default
    port_default = get_webhook_reliability_port()
    assert port_default._max_attempts == DEFAULT_MAX_ATTEMPTS  # type: ignore[attr-defined]
    assert port_default._max_attempts == 3  # type: ignore[attr-defined]

    # EDD critical override (ADR-034 §matrix x5)
    monkeypatch.setenv("WEBHOOK_MAX_ATTEMPTS", "5")
    get_webhook_reliability_port.cache_clear()
    port_edd = get_webhook_reliability_port()
    assert port_edd._max_attempts == 5  # type: ignore[attr-defined]


def test_di_singleton_scope_lru_cache_returns_same_instance() -> None:
    a = get_webhook_reliability_port()
    b = get_webhook_reliability_port()
    assert a is b


def test_di_redis_adapter_resolves_after_step4(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR-034 Step 4 wires the 'redis' branch — no more NotImplementedError."""
    from services.webhooks.redis_adapter import RedisWebhookReliabilityAdapter

    monkeypatch.setenv("WEBHOOK_RELIABILITY_ADAPTER", "redis")
    # redis.Redis.from_url() does not connect until the first command, so this
    # is safe with no real Redis available in the test environment.
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    get_webhook_reliability_port.cache_clear()
    port = get_webhook_reliability_port()
    assert isinstance(port, RedisWebhookReliabilityAdapter)


def test_di_unknown_adapter_raises_not_implemented(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Genuinely unknown adapter values still raise NotImplementedError."""
    monkeypatch.setenv("WEBHOOK_RELIABILITY_ADAPTER", "kafka")
    get_webhook_reliability_port.cache_clear()
    with pytest.raises(NotImplementedError, match="'in_memory' and 'redis'"):
        get_webhook_reliability_port()
