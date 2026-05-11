"""
in_memory_adapter.py — In-memory WebhookReliabilityPort adapter.

Test/dev double for the production Redis+DLQ adapter (ADR-034 Step 4).
Pure in-process: dict-backed storage, deterministic clock injection,
no network, no DB, no logging side effects.

Backoff policy (ADR-034 §Webhook reliability matrix):
  default schedule [1.0, 10.0, 60.0]  (×3 attempts, non-EDD)
  EDD caller overrides via constructor (e.g. ×5 for applicantActionPending)

On mark_failed:
  - increment attempt
  - if attempt >= max_attempts → status = "dead"
  - else → schedule next_retry_at = now() + schedule[attempt-1]

next_due returns records with status == "pending" AND
next_retry_at <= now_ts, ordered ascending by next_retry_at, capped.
"""

from __future__ import annotations

from collections.abc import Callable
import time

from services.webhooks.reliability_port import (
    WebhookDeliveryRecord,
    WebhookReliabilityPort,
)

DEFAULT_BACKOFF_SCHEDULE: tuple[float, ...] = (1.0, 10.0, 60.0)
DEFAULT_MAX_ATTEMPTS: int = 3


class InMemoryWebhookAdapter(WebhookReliabilityPort):
    """In-memory adapter for WebhookReliabilityPort.

    Args:
      backoff_schedule: seconds-to-wait per attempt index. The Nth retry
          (1-based) waits `backoff_schedule[N-1]` seconds. If attempts
          exceed schedule length, last entry repeats up to max_attempts.
      max_attempts: total attempts allowed (initial + retries). After this,
          status transitions to "dead".
      clock: callable returning current epoch seconds. Defaults to time.time;
          tests inject a deterministic closure.
    """

    def __init__(
        self,
        backoff_schedule: tuple[float, ...] = DEFAULT_BACKOFF_SCHEDULE,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if not backoff_schedule:
            raise ValueError("backoff_schedule must be non-empty")
        self._records: dict[str, WebhookDeliveryRecord] = {}
        self._backoff = backoff_schedule
        self._max_attempts = max_attempts
        self._clock = clock

    def enqueue(
        self,
        event_id: str,
        payload: dict,
        target_url: str,
        attempt: int = 0,
    ) -> None:
        self._records[event_id] = WebhookDeliveryRecord(
            event_id=event_id,
            payload=payload,
            target_url=target_url,
            attempt=attempt,
            next_retry_at=self._clock(),
            status="pending",
            last_error="",
        )

    def mark_delivered(self, event_id: str) -> None:
        record = self._records.get(event_id)
        if record is None:
            return
        record.status = "delivered"
        record.last_error = ""

    def mark_failed(self, event_id: str, error: str) -> None:
        record = self._records.get(event_id)
        if record is None:
            return
        record.attempt += 1
        record.last_error = error
        if record.attempt >= self._max_attempts:
            record.status = "dead"
            return
        backoff_index = min(record.attempt - 1, len(self._backoff) - 1)
        record.next_retry_at = self._clock() + self._backoff[backoff_index]

    def next_due(self, now_ts: float, limit: int) -> list[WebhookDeliveryRecord]:
        if limit <= 0:
            return []
        eligible = [
            r for r in self._records.values() if r.status == "pending" and r.next_retry_at <= now_ts
        ]
        eligible.sort(key=lambda r: r.next_retry_at)
        return eligible[:limit]
