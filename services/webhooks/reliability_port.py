"""
reliability_port.py — Webhook delivery reliability port (ADR-034 Step 1).

Defines the abstract Port over webhook delivery reliability semantics:
  - enqueue: register a delivery attempt
  - mark_delivered: terminal success
  - mark_failed: schedule next retry with exponential backoff, or mark dead
  - next_due: list pending records eligible for redelivery at a given clock

Per ADR-034 §Implementation Plan, the production adapter binds to Redis
(SETNX idempotency + RPUSH/BLPOP queue) and the existing DLQ. This Port
abstracts those semantics so the cron/worker layer (ADR-034 Steps 2-5)
can be DI-wired and tested without Redis.

Default retry policy follows ADR-034 §Webhook reliability matrix:
  - Non-EDD events: max 3 attempts, backoff [1s, 10s, 60s]
  - EDD critical (applicantActionPending): max 5 attempts (caller-supplied)

No I/O. No side effects. Pure typing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

WebhookStatus = str  # one of: "pending", "delivered", "dead"


@dataclass
class WebhookDeliveryRecord:
    """A single inbound/outbound webhook delivery attempt record.

    Fields:
      event_id:       provider-supplied or idempotency-key-derived identifier
      payload:        opaque event body (provider-specific shape)
      target_url:     destination for outbound; provider URL for inbound replay
      attempt:        zero-based count of attempts already executed
      next_retry_at:  epoch seconds when this record is eligible for redelivery
      status:         "pending" | "delivered" | "dead"
      last_error:     last failure message (empty string if none)
    """

    event_id: str
    payload: dict
    target_url: str
    attempt: int = 0
    next_retry_at: float = 0.0
    status: WebhookStatus = "pending"
    last_error: str = ""


class WebhookReliabilityPort(Protocol):
    """Port abstracting webhook delivery reliability (ADR-034)."""

    def enqueue(
        self,
        event_id: str,
        payload: dict,
        target_url: str,
        attempt: int = 0,
    ) -> None:
        """Register a delivery record in pending state."""
        ...

    def mark_delivered(self, event_id: str) -> None:
        """Terminal success: mark record as delivered."""
        ...

    def mark_failed(self, event_id: str, error: str) -> None:
        """Failure: increment attempt; schedule next retry per backoff
        schedule; if attempts exhausted, transition to 'dead'."""
        ...

    def next_due(self, now_ts: float, limit: int) -> list[WebhookDeliveryRecord]:
        """Return pending records with next_retry_at <= now_ts, ordered by
        next_retry_at ascending, capped by `limit`."""
        ...
