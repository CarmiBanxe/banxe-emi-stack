"""
async_worker.py — Asynchronous webhook delivery worker (ADR-034 Step 3).

Transport-agnostic worker loop:
  port.next_due(now, batch)  →  client.deliver(...)  →  port.mark_delivered |
                                                        port.mark_failed

ADR-034 §Implementation-Plan item 4 describes a SumSub-specific worker that
consumes a Redis BLPOP queue. This module is the generic, Port-driven variant
the DI binds in Step 2; the Redis-specific worker (and DLQ + Telegram alert
on exhaustion) is deferred to ADR-034 Step 4.

Defaults (ADR-034 silent on these; per Step 3 prompt):
  poll_interval_seconds = 1.0
  batch_limit           = 50
  delivery_timeout_s    = 10.0

No global state. No logging side effects. No real-time dependency:
clock is injected so tests stay deterministic.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import time

from services.webhooks.delivery_client import WebhookDeliveryClient
from services.webhooks.reliability_port import WebhookReliabilityPort


class WebhookAsyncWorker:
    """Drives delivery attempts from the WebhookReliabilityPort queue."""

    def __init__(
        self,
        port: WebhookReliabilityPort,
        client: WebhookDeliveryClient,
        clock: Callable[[], float] = time.time,
        poll_interval_s: float = 1.0,
        batch_limit: int = 50,
        delivery_timeout_s: float = 10.0,
    ) -> None:
        if poll_interval_s < 0:
            raise ValueError("poll_interval_s must be >= 0")
        if batch_limit < 1:
            raise ValueError("batch_limit must be >= 1")
        if delivery_timeout_s <= 0:
            raise ValueError("delivery_timeout_s must be > 0")
        self._port = port
        self._client = client
        self._clock = clock
        self._poll_interval_s = poll_interval_s
        self._batch_limit = batch_limit
        self._delivery_timeout_s = delivery_timeout_s

    async def run_once(self) -> int:
        """Process at most `batch_limit` due records. Returns count processed."""
        due = self._port.next_due(self._clock(), self._batch_limit)
        for record in due:
            try:
                result = await self._client.deliver(
                    record.target_url,
                    record.payload,
                    self._delivery_timeout_s,
                )
            except Exception as exc:
                self._port.mark_failed(record.event_id, f"exception: {exc!r}")
                continue
            if result.success:
                self._port.mark_delivered(record.event_id)
            else:
                err = result.error or f"non-success status={result.status_code}"
                self._port.mark_failed(record.event_id, err)
        return len(due)

    async def run_forever(self, stop_event: asyncio.Event) -> None:
        """Loop run_once + sleep until stop_event is set."""
        while not stop_event.is_set():
            await self.run_once()
            if self._poll_interval_s <= 0:
                await asyncio.sleep(0)
                continue
            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=self._poll_interval_s,
                )
            except TimeoutError:
                continue
