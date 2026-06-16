"""
test_webhook_reliability_smoke.py — End-to-end smoke for ADR-034 (Step 5).

Exercises the full Port → DI → Worker → Redis → DLQ → Alert chain without any
real Redis instance, HTTP traffic, or real time.sleep:

  Step 1 Port:        WebhookReliabilityPort + WebhookDeliveryRecord
  Step 2 DI:          api.deps.get_webhook_reliability_port
  Step 3 Worker:      WebhookAsyncWorker (run_once on Port-driven queue)
  Step 4 Redis:       RedisWebhookReliabilityAdapter + FakeRedis double
  Step 4 HTTP:        WebhookDeliveryClient Protocol (in-memory double here)
  Step 4 DLQ + Alert: webhook:dlq list + TelegramDLQAlertHook + InMemoryAlertAdapter

Repo runs pytest-asyncio in asyncio_mode = "auto", so async test functions
execute without explicit decoration.
"""

from __future__ import annotations

import asyncio

import pytest

from api.deps import get_webhook_reliability_port
from services.alerting.alert_port import AlertSeverity
from services.alerting.in_memory_adapter import InMemoryAlertAdapter
from services.webhooks.async_worker import WebhookAsyncWorker
from services.webhooks.delivery_client import DeliveryResult, WebhookDeliveryClient
from services.webhooks.dlq_alert import TelegramDLQAlertHook
from services.webhooks.in_memory_adapter import InMemoryWebhookAdapter
from services.webhooks.inmemory_delivery_client import InMemoryDeliveryClient
from services.webhooks.redis_adapter import (
    DEDUP_KEY_PREFIX,
    DLQ_KEY,
    RECORD_KEY_PREFIX,
    RedisWebhookReliabilityAdapter,
)
from tests.unit.webhooks._fakes import FakeRedis

pytestmark = pytest.mark.smoke


async def test_smoke_enqueue_through_worker_to_delivered() -> None:
    """Happy path: enqueue → worker → client success → mark_delivered."""
    clock = [1000.0]
    port = InMemoryWebhookAdapter(clock=lambda: clock[0])
    client = InMemoryDeliveryClient(behavior={"https://kc/hook": "success"})
    worker = WebhookAsyncWorker(
        port=port, client=client, clock=lambda: clock[0], poll_interval_s=0.0
    )

    port.enqueue("ev-1", {"applicantId": "a1"}, "https://kc/hook")
    processed = await worker.run_once()

    assert processed == 1
    assert port.next_due(now_ts=clock[0] + 10_000, limit=10) == []
    assert port._records["ev-1"].status == "delivered"  # type: ignore[attr-defined]
    assert len(client.attempts["https://kc/hook"]) == 1


async def test_smoke_retry_path_until_success() -> None:
    """Client fails twice, then succeeds — retry schedule honoured by Port."""
    clock = [0.0]
    port = InMemoryWebhookAdapter(
        backoff_schedule=(1.0, 10.0, 60.0),
        max_attempts=3,
        clock=lambda: clock[0],
    )

    class TwoFailsThenSuccess(WebhookDeliveryClient):
        def __init__(self) -> None:
            self.call_count = 0

        async def deliver(self, target_url: str, payload: dict, timeout_s: float) -> DeliveryResult:
            self.call_count += 1
            if self.call_count <= 2:
                return DeliveryResult(success=False, status_code=503, error="upstream 503")
            return DeliveryResult(success=True, status_code=200)

    client = TwoFailsThenSuccess()
    worker = WebhookAsyncWorker(
        port=port, client=client, clock=lambda: clock[0], poll_interval_s=0.0
    )

    port.enqueue("ev-1", {}, "https://x")

    # Sweep 1 @ t=0: fail → attempt=1, next_retry=0+1=1
    assert await worker.run_once() == 1
    assert port._records["ev-1"].attempt == 1  # type: ignore[attr-defined]
    assert port._records["ev-1"].next_retry_at == 1.0  # type: ignore[attr-defined]
    # Before backoff elapses: nothing due
    assert await worker.run_once() == 0

    # Advance past first backoff
    clock[0] = 1.0
    # Sweep 2 @ t=1: fail → attempt=2, next_retry=1+10=11
    assert await worker.run_once() == 1
    assert port._records["ev-1"].attempt == 2  # type: ignore[attr-defined]
    assert port._records["ev-1"].next_retry_at == 11.0  # type: ignore[attr-defined]

    # Advance past second backoff
    clock[0] = 11.0
    # Sweep 3 @ t=11: success → mark_delivered
    assert await worker.run_once() == 1
    assert port._records["ev-1"].status == "delivered"  # type: ignore[attr-defined]
    assert client.call_count == 3


async def test_smoke_exhaustion_pushes_to_dlq_and_fires_alert() -> None:
    """Redis adapter: client always fails → max_attempts reached → DLQ + critical alert."""
    clock = [0.0]
    fake = FakeRedis(clock=lambda: clock[0])
    alert_sink = InMemoryAlertAdapter()
    dlq_hook = TelegramDLQAlertHook(alert_port=alert_sink)
    port = RedisWebhookReliabilityAdapter(
        redis_client=fake,
        max_attempts=2,
        backoff_schedule=(1.0, 1.0),
        dlq_alert_hook=dlq_hook,
        dedup_ttl_s=3600,
        clock=lambda: clock[0],
    )
    client = InMemoryDeliveryClient(behavior={"https://kc/hook": "fail"})
    worker = WebhookAsyncWorker(
        port=port, client=client, clock=lambda: clock[0], poll_interval_s=0.0
    )

    port.enqueue("ev-1", {"applicantId": "a1"}, "https://kc/hook")
    # Sweep 1: fail → attempt=1
    assert await worker.run_once() == 1
    # Advance past backoff
    clock[0] = 1.0
    # Sweep 2: fail → attempt=2 == max → DLQ + alert
    assert await worker.run_once() == 1

    # Active record is gone, DLQ has the snapshot
    assert fake.hgetall(RECORD_KEY_PREFIX + "ev-1") == {}
    dlq = fake.lrange(DLQ_KEY, 0, -1)
    assert len(dlq) == 1
    assert "ev-1" in dlq[0]

    # Let the asyncio.create_task scheduled by the alert hook complete
    for _ in range(10):
        await asyncio.sleep(0)
    assert len(alert_sink.alerts) == 1
    alert = alert_sink.alerts[0]
    assert alert.severity == AlertSeverity.CRITICAL
    assert "event_id=ev-1" in alert.body
    assert "attempts=2" in alert.body


def test_smoke_dedup_setnx_blocks_duplicate_event_id() -> None:
    """Redis SETNX dedup: same event_id enqueued twice → only one record."""
    fake = FakeRedis()
    port = RedisWebhookReliabilityAdapter(
        redis_client=fake,
        max_attempts=3,
        backoff_schedule=(1.0,),
        dedup_ttl_s=86400,
    )
    port.enqueue("ev-1", {"v": "first"}, "https://x")
    port.enqueue("ev-1", {"v": "second"}, "https://x")  # duplicate — must be ignored

    rec = fake.hgetall(RECORD_KEY_PREFIX + "ev-1")
    assert rec["event_id"] == "ev-1"
    import json

    assert json.loads(rec["payload"]) == {"v": "first"}
    assert fake.exists(DEDUP_KEY_PREFIX + "ev-1") == 1


async def test_smoke_batch_limit_respected_in_run_once() -> None:
    """Worker.run_once processes at most batch_limit records per sweep."""
    clock = [0.0]
    port = InMemoryWebhookAdapter(clock=lambda: clock[0])
    client = InMemoryDeliveryClient(behavior={"https://x": "success"})
    worker = WebhookAsyncWorker(
        port=port,
        client=client,
        clock=lambda: clock[0],
        poll_interval_s=0.0,
        batch_limit=3,
    )

    for i in range(7):
        port.enqueue(f"ev-{i}", {}, "https://x")

    # Sweep 1: 3 processed
    assert await worker.run_once() == 3
    # Remaining due: 4
    assert len(port.next_due(now_ts=clock[0] + 1, limit=100)) == 4
    # Sweep 2: 3 more
    assert await worker.run_once() == 3
    # Remaining: 1
    assert len(port.next_due(now_ts=clock[0] + 1, limit=100)) == 1
    # Sweep 3: last 1
    assert await worker.run_once() == 1
    assert port.next_due(now_ts=clock[0] + 10_000, limit=100) == []


def test_smoke_di_resolves_redis_adapter_with_step4_wiring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DI: WEBHOOK_RELIABILITY_ADAPTER=redis returns RedisWebhookReliabilityAdapter
    with env-driven max_attempts / backoff / dedup_ttl."""
    monkeypatch.setenv("WEBHOOK_RELIABILITY_ADAPTER", "redis")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("WEBHOOK_MAX_ATTEMPTS", "5")
    monkeypatch.setenv("WEBHOOK_BACKOFF_SECONDS", "2.0,8.0,30.0")
    monkeypatch.setenv("WEBHOOK_DEDUP_TTL_SECONDS", "3600")
    get_webhook_reliability_port.cache_clear()
    try:
        adapter = get_webhook_reliability_port()
        assert isinstance(adapter, RedisWebhookReliabilityAdapter)
        # All four env knobs reflected on the constructed adapter
        assert adapter._max_attempts == 5  # type: ignore[attr-defined]
        assert adapter._backoff == (2.0, 8.0, 30.0)  # type: ignore[attr-defined]
        assert adapter._dedup_ttl == 3600  # type: ignore[attr-defined]
        # Alert hook is wired (Step 4)
        assert adapter._dlq_alert is not None  # type: ignore[attr-defined]
    finally:
        get_webhook_reliability_port.cache_clear()
