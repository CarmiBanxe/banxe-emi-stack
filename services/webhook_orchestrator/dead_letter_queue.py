"""
services/webhook_orchestrator/dead_letter_queue.py — Dead Letter Queue
IL-WHO-01 | Phase 28 | banxe-emi-stack

Append-only dead letter queue for undeliverable webhook events. In prod uses
ClickHouse (I-24). Manual retry creates a new PENDING attempt — old DLQ entry
is never deleted (append-only invariant).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
import uuid

from services.webhook_orchestrator.models import (
    DeliveryAttempt,
    DeliveryStatus,
    DeliveryStorePort,
    InMemoryDeliveryStore,
)


@dataclass
class DeadLetterQueue:
    """Manages dead-lettered webhook delivery attempts.

    Invariant I-24: DLQ records are append-only — never deleted.
    ClickHouse append-only table in prod. InMemory in tests.
    """

    delivery_store: DeliveryStorePort

    def __init__(self, delivery_store: DeliveryStorePort | None = None) -> None:
        self.delivery_store: DeliveryStorePort = delivery_store or InMemoryDeliveryStore()

    def enqueue(self, attempt: DeliveryAttempt) -> DeliveryAttempt:
        """Move a failed attempt to dead letter status and persist.

        NOTE: ClickHouse append-only in prod (I-24). InMemory update in test.
        """
        dead = replace(
            attempt,
            status=DeliveryStatus.DEAD_LETTER,
            attempted_at=datetime.now(UTC),
        )
        self.delivery_store.update(dead)
        return dead

    def list_dlq(self, limit: int = 50) -> list[DeliveryAttempt]:
        """Return all DEAD_LETTER attempts up to limit."""
        failed = self.delivery_store.list_failed(limit)
        return [d for d in failed if d.status == DeliveryStatus.DEAD_LETTER]

    def retry_from_dlq(self, attempt_id: str) -> DeliveryAttempt:
        """Create a new PENDING attempt from a DLQ entry (old entry remains).

        Invariant I-24: original DLQ record is never deleted.

        Raises:
            ValueError: if attempt_id not found or not in DEAD_LETTER status.
        """
        original = self.delivery_store.get(attempt_id)
        if original is None:
            raise ValueError(f"Attempt not found: {attempt_id}")
        if original.status != DeliveryStatus.DEAD_LETTER:
            raise ValueError(
                f"Attempt {attempt_id} is not in DEAD_LETTER status (current: {original.status})"
            )

        new_attempt = DeliveryAttempt(
            attempt_id=str(uuid.uuid4()),
            event_id=original.event_id,
            subscription_id=original.subscription_id,
            status=DeliveryStatus.PENDING,
            http_status=None,
            attempt_number=1,
            response_body="",
            attempted_at=datetime.now(UTC),
            next_retry_at=None,
        )
        self.delivery_store.save(new_attempt)
        return new_attempt

    def get_dlq_stats(self) -> dict:
        """Return DLQ statistics: total count and breakdown by subscription."""
        dlq_items = self.list_dlq(limit=10_000)  # large cap to approximate "all"
        by_subscription: dict[str, int] = {}
        for item in dlq_items:
            by_subscription[item.subscription_id] = by_subscription.get(item.subscription_id, 0) + 1
        return {
            "total_dead_letter": len(dlq_items),
            "by_subscription": by_subscription,
        }
