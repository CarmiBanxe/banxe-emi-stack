"""
services/webhook_orchestrator/delivery_engine.py — Webhook Delivery Engine
IL-WHO-01 | Phase 28 | banxe-emi-stack

Handles webhook delivery with exponential backoff retry (6 attempts) and
circuit breaker per subscription. Dead-letter after max retries exhausted.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
import uuid

from services.webhook_orchestrator.models import (
    CircuitBreakerStorePort,
    CircuitState,
    DeliveryAttempt,
    DeliveryStatus,
    DeliveryStorePort,
    InMemoryCircuitBreakerStore,
    InMemoryDeliveryStore,
    WebhookEvent,
    WebhookSubscription,
)

# Retry schedule in seconds: [1, 5, 30, 300, 1800, 7200] — 6 attempts total
RETRY_SCHEDULE: list[int] = [1, 5, 30, 300, 1800, 7200]
MAX_ATTEMPTS: int = 6


@dataclass
class DeliveryEngine:
    """Handles webhook delivery with circuit breaker and retry logic.

    Circuit breaker is per-subscription. When OPEN, deliveries are skipped
    until the circuit moves to HALF_OPEN or CLOSED.
    """

    delivery_store: DeliveryStorePort
    circuit_store: CircuitBreakerStorePort

    def __init__(
        self,
        delivery_store: DeliveryStorePort | None = None,
        circuit_store: CircuitBreakerStorePort | None = None,
    ) -> None:
        self.delivery_store: DeliveryStorePort = delivery_store or InMemoryDeliveryStore()
        self.circuit_store: CircuitBreakerStorePort = circuit_store or InMemoryCircuitBreakerStore()

    def deliver(
        self,
        attempt: DeliveryAttempt,
        subscription: WebhookSubscription,
        event: WebhookEvent,  # noqa: ARG002
    ) -> DeliveryAttempt:
        """Attempt delivery of a webhook event to a subscription endpoint.

        Circuit breaker check: if OPEN, skip delivery and return FAILED.
        InMemory stub: always succeeds (http_status=200, DELIVERED).
        On success: reset circuit breaker failure counter.
        """
        circuit_state = self.circuit_store.get_state(subscription.subscription_id)

        if circuit_state == CircuitState.OPEN:
            failed = replace(
                attempt,
                status=DeliveryStatus.FAILED,
                http_status=None,
                response_body="Circuit breaker OPEN — delivery skipped",
                attempted_at=datetime.now(UTC),
            )
            self.delivery_store.update(failed)
            return failed

        # InMemory stub: simulate successful delivery
        delivered = replace(
            attempt,
            status=DeliveryStatus.DELIVERED,
            http_status=200,
            response_body='{"ok": true}',
            attempted_at=datetime.now(UTC),
        )
        self.delivery_store.update(delivered)
        self.circuit_store.reset_failures(subscription.subscription_id)
        return delivered

    def schedule_retry(self, attempt: DeliveryAttempt) -> DeliveryAttempt | None:
        """Schedule the next retry or move to dead letter after MAX_ATTEMPTS.

        Returns new RETRYING attempt, or None if moved to dead letter.
        """
        if attempt.attempt_number >= MAX_ATTEMPTS:
            return None  # Caller should enqueue to DLQ

        next_delay = self.get_retry_delay(attempt.attempt_number)
        next_retry_at = datetime.now(UTC) + timedelta(seconds=next_delay)

        new_attempt = DeliveryAttempt(
            attempt_id=str(uuid.uuid4()),
            event_id=attempt.event_id,
            subscription_id=attempt.subscription_id,
            status=DeliveryStatus.RETRYING,
            http_status=None,
            attempt_number=attempt.attempt_number + 1,
            response_body="",
            attempted_at=datetime.now(UTC),
            next_retry_at=next_retry_at,
        )
        self.delivery_store.save(new_attempt)
        return new_attempt

    def get_retry_delay(self, attempt_number: int) -> int:
        """Return retry delay in seconds for the given attempt number (1-indexed).

        Schedule: [1, 5, 30, 300, 1800, 7200] — attempt_number 1 → 1s, 6 → 7200s.
        """
        idx = max(0, min(attempt_number - 1, len(RETRY_SCHEDULE) - 1))
        return RETRY_SCHEDULE[idx]
