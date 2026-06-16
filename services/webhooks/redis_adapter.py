"""
redis_adapter.py — Redis-backed WebhookReliabilityPort (ADR-034 Step 4).

Storage layout (generic across providers; SumSub-specific topic naming
from ADR-034 §Implementation-Plan item 3 applies at the route/handler
layer when keys are populated, not in this Port abstraction):

  webhook:dedup:{event_id}    String, SETNX guard with EX TTL (default 24h)
  webhook:record:{event_id}   Hash:
                                event_id, payload (json), target_url,
                                attempt, next_retry_at, status, last_error
  webhook:due                 SortedSet: member=event_id, score=next_retry_at
  webhook:dlq                 List: LPUSH json-snapshot on exhaustion

Exhaustion semantics:
  attempt >= max_attempts → status = "dead":
    * push JSON snapshot to webhook:dlq
    * delete record hash + zrem from due
    * fire dlq_alert_hook(record) — exceptions swallowed so alert failures
      cannot break the delivery loop (ADR-034 silent on this; default = swallow)

Pure Redis-protocol calls; no HTTP; no logging side effects.
"""

from __future__ import annotations

from collections.abc import Callable
import contextlib
import json
import time
from typing import Any

from services.webhooks.reliability_port import (
    WebhookDeliveryRecord,
    WebhookReliabilityPort,
)

RECORD_KEY_PREFIX = "webhook:record:"
DUE_KEY = "webhook:due"
DLQ_KEY = "webhook:dlq"
DEDUP_KEY_PREFIX = "webhook:dedup:"

DLQAlertHook = Callable[[WebhookDeliveryRecord], None]


class RedisWebhookReliabilityAdapter(WebhookReliabilityPort):
    """Redis-backed implementation of WebhookReliabilityPort.

    Args:
      redis_client:     a redis client supporting set/hset/hgetall/delete/
                        zadd/zrem/zrangebyscore/lpush — typed loosely as Any
                        to permit injection of fakes in tests.
      max_attempts:     attempts allowed before transition to dead state.
      backoff_schedule: per-attempt seconds-to-wait; last entry repeats.
      dlq_alert_hook:   optional sync callable invoked on exhaustion. Exceptions
                        from the hook are swallowed so a misfiring alert sink
                        cannot break webhook delivery.
      dedup_ttl_s:      SETNX dedup TTL (default 86400 per ADR-034 §c).
      clock:            epoch-seconds source; injected for deterministic tests.
    """

    def __init__(
        self,
        redis_client: Any,
        max_attempts: int = 3,
        backoff_schedule: tuple[float, ...] = (1.0, 10.0, 60.0),
        dlq_alert_hook: DLQAlertHook | None = None,
        dedup_ttl_s: int = 86400,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if not backoff_schedule:
            raise ValueError("backoff_schedule must be non-empty")
        if dedup_ttl_s < 1:
            raise ValueError("dedup_ttl_s must be >= 1")
        self._r = redis_client
        self._max_attempts = max_attempts
        self._backoff = backoff_schedule
        self._dlq_alert = dlq_alert_hook
        self._dedup_ttl = dedup_ttl_s
        self._clock = clock

    def enqueue(
        self,
        event_id: str,
        payload: dict,
        target_url: str,
        attempt: int = 0,
    ) -> None:
        # Idempotency guard (ADR-034 §c step 3): SETNX with TTL.
        ok = self._r.set(
            DEDUP_KEY_PREFIX + event_id,
            "1",
            nx=True,
            ex=self._dedup_ttl,
        )
        if not ok:
            return  # duplicate delivery — silently skip
        now = self._clock()
        self._r.hset(
            RECORD_KEY_PREFIX + event_id,
            mapping={
                "event_id": event_id,
                "payload": json.dumps(payload),
                "target_url": target_url,
                "attempt": str(attempt),
                "next_retry_at": str(now),
                "status": "pending",
                "last_error": "",
            },
        )
        self._r.zadd(DUE_KEY, {event_id: now})

    def mark_delivered(self, event_id: str) -> None:
        self._r.delete(RECORD_KEY_PREFIX + event_id)
        self._r.zrem(DUE_KEY, event_id)

    def mark_failed(self, event_id: str, error: str) -> None:
        h = self._r.hgetall(RECORD_KEY_PREFIX + event_id)
        if not h:
            return
        attempt = int(h.get("attempt", "0")) + 1
        if attempt >= self._max_attempts:
            # Build snapshot before deletion (for DLQ payload + alert).
            record = self._to_record(
                h,
                override={
                    "attempt": str(attempt),
                    "status": "dead",
                    "last_error": error,
                },
            )
            self._r.lpush(
                DLQ_KEY,
                json.dumps(
                    {
                        "event_id": record.event_id,
                        "payload": record.payload,
                        "target_url": record.target_url,
                        "attempt": record.attempt,
                        "next_retry_at": record.next_retry_at,
                        "status": "dead",
                        "last_error": record.last_error,
                    }
                ),
            )
            self._r.delete(RECORD_KEY_PREFIX + event_id)
            self._r.zrem(DUE_KEY, event_id)
            if self._dlq_alert is not None:
                # Swallow: a broken alert sink must not break delivery.
                with contextlib.suppress(Exception):
                    self._dlq_alert(record)
            return
        idx = min(attempt - 1, len(self._backoff) - 1)
        next_retry = self._clock() + self._backoff[idx]
        self._r.hset(
            RECORD_KEY_PREFIX + event_id,
            mapping={
                "attempt": str(attempt),
                "next_retry_at": str(next_retry),
                "last_error": error,
            },
        )
        self._r.zadd(DUE_KEY, {event_id: next_retry})

    def next_due(self, now_ts: float, limit: int) -> list[WebhookDeliveryRecord]:
        if limit <= 0:
            return []
        members = self._r.zrangebyscore(
            DUE_KEY,
            min=0,
            max=now_ts,
            start=0,
            num=limit,
        )
        out: list[WebhookDeliveryRecord] = []
        for event_id in members:
            h = self._r.hgetall(RECORD_KEY_PREFIX + event_id)
            if not h or h.get("status") != "pending":
                continue
            out.append(self._to_record(h))
        return out

    def _to_record(
        self,
        h: dict,
        override: dict | None = None,
    ) -> WebhookDeliveryRecord:
        data = dict(h)
        if override:
            data.update(override)
        return WebhookDeliveryRecord(
            event_id=data["event_id"],
            payload=json.loads(data.get("payload", "{}")),
            target_url=data.get("target_url", ""),
            attempt=int(data.get("attempt", "0")),
            next_retry_at=float(data.get("next_retry_at", "0")),
            status=data.get("status", "pending"),
            last_error=data.get("last_error", ""),
        )
