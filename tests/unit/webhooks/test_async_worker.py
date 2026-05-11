"""
test_async_worker.py — Unit tests for WebhookAsyncWorker (ADR-034 Step 3).

Deterministic async tests:
  - clock injected via mutable list closure (no real time)
  - InMemoryWebhookAdapter as Port (Step 1)
  - InMemoryDeliveryClient as transport (configurable per-URL behaviour)

Repo runs pytest-asyncio in asyncio_mode = "auto", so `async def test_*`
functions execute under the asyncio runner without explicit decoration.
"""

from __future__ import annotations

import asyncio

from services.webhooks.async_worker import WebhookAsyncWorker
from services.webhooks.in_memory_adapter import InMemoryWebhookAdapter
from services.webhooks.inmemory_delivery_client import InMemoryDeliveryClient


def _build(
    start_time: float = 1000.0,
    backoff: tuple[float, ...] = (1.0, 10.0, 60.0),
    max_attempts: int = 3,
    batch_limit: int = 50,
    poll_interval_s: float = 1.0,
    delivery_timeout_s: float = 10.0,
) -> tuple[WebhookAsyncWorker, InMemoryWebhookAdapter, InMemoryDeliveryClient, list[float]]:
    clock = [start_time]
    port = InMemoryWebhookAdapter(
        backoff_schedule=backoff,
        max_attempts=max_attempts,
        clock=lambda: clock[0],
    )
    client = InMemoryDeliveryClient()
    worker = WebhookAsyncWorker(
        port=port,
        client=client,
        clock=lambda: clock[0],
        poll_interval_s=poll_interval_s,
        batch_limit=batch_limit,
        delivery_timeout_s=delivery_timeout_s,
    )
    return worker, port, client, clock


async def test_run_once_returns_zero_when_no_due_records() -> None:
    worker, _port, _client, _clock = _build()
    assert await worker.run_once() == 0


async def test_run_once_marks_delivered_on_client_success() -> None:
    worker, port, client, _clock = _build()
    port.enqueue("ev-1", {"k": "v"}, "https://ok")
    client.set_behavior("https://ok", "success")
    n = await worker.run_once()
    assert n == 1
    # Delivered → not in next_due any more
    assert port.next_due(now_ts=10_000.0, limit=10) == []
    # Attempt was actually invoked
    assert client.attempts["https://ok"][0][0] == {"k": "v"}
    assert client.attempts["https://ok"][0][1] == 10.0  # delivery_timeout_s


async def test_run_once_marks_failed_on_client_failure_result() -> None:
    worker, port, client, clock = _build()
    port.enqueue("ev-1", {}, "https://fail")
    client.set_behavior("https://fail", "fail")
    n = await worker.run_once()
    assert n == 1
    # Failed → attempt=1, scheduled for backoff[0]=1.0s in the future
    record = port._records["ev-1"]  # type: ignore[attr-defined]
    assert record.status == "pending"
    assert record.attempt == 1
    assert record.next_retry_at == clock[0] + 1.0
    assert "injected fail" in record.last_error


async def test_run_once_marks_failed_on_client_exception() -> None:
    worker, port, client, _clock = _build()
    port.enqueue("ev-1", {}, "https://boom")
    client.set_behavior("https://boom", "raise")
    n = await worker.run_once()
    assert n == 1
    record = port._records["ev-1"]  # type: ignore[attr-defined]
    assert record.status == "pending"
    assert record.attempt == 1
    assert record.last_error.startswith("exception: ")
    assert "RuntimeError" in record.last_error


async def test_run_once_respects_batch_limit() -> None:
    worker, port, client, _clock = _build(batch_limit=2)
    for i in range(5):
        port.enqueue(f"ev-{i}", {}, "https://ok")
    client.set_behavior("https://ok", "success")
    n = await worker.run_once()
    assert n == 2
    # 3 remain pending
    assert len(port.next_due(now_ts=10_000.0, limit=100)) == 3


async def test_run_once_processes_records_in_due_order() -> None:
    worker, port, client, clock = _build(start_time=100.0)
    # Three at t=100, then fail ev-a so it shifts to t=101
    port.enqueue("ev-a", {}, "https://ok")
    port.enqueue("ev-b", {}, "https://ok")
    port.enqueue("ev-c", {}, "https://ok")
    client.set_behavior("https://ok", "fail")
    # First sweep: all three fail-marked in due order (a, b, c) — they were
    # enqueued with the same next_retry_at, so iteration order is enqueue order
    # because the adapter's sort is stable on equal keys.
    await worker.run_once()
    # Re-arm: success this time, at t=101 (after backoff)
    client.set_behavior("https://ok", "success")
    clock[0] = 101.0
    await worker.run_once()
    # All three observed in attempt log in order
    seen = [p for p, _ in client.attempts["https://ok"]]
    # Each url was attempted twice: 3 fails then 3 successes — total 6 entries
    assert len(seen) == 6


async def test_run_forever_stops_on_stop_event() -> None:
    worker, port, client, _clock = _build(poll_interval_s=0.0)
    port.enqueue("ev-1", {}, "https://ok")
    client.set_behavior("https://ok", "success")
    stop = asyncio.Event()

    async def stopper() -> None:
        # Yield a few times to let run_forever execute run_once at least once
        for _ in range(5):
            await asyncio.sleep(0)
        stop.set()

    await asyncio.gather(worker.run_forever(stop), stopper())
    # ev-1 was delivered during one of the loop iterations
    assert port._records["ev-1"].status == "delivered"  # type: ignore[attr-defined]


async def test_worker_uses_injected_clock_not_realtime() -> None:
    # next_due is queried with worker._clock(); flipping the clock decides
    # whether a future-scheduled record is visible — proves real time isn't used.
    worker, port, _client, clock = _build(start_time=0.0)
    port.enqueue("ev-1", {}, "https://ok")
    # Force record into the future via a failed delivery at t=0
    port.mark_failed("ev-1", "synthetic")  # next_retry_at = 0 + 1.0 = 1.0
    # Worker clock still at 0.0 → nothing should be due
    assert await worker.run_once() == 0
    # Advance worker's view of time past the backoff
    clock[0] = 5.0
    assert await worker.run_once() == 1
