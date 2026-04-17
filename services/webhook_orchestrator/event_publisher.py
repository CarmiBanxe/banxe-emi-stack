"""
services/webhook_orchestrator/event_publisher.py — Webhook Event Publisher
IL-WHO-01 | Phase 28 | banxe-emi-stack

Publishes webhook events with idempotency guarantees. Fan-out: one event →
one DeliveryAttempt per matching subscription. Protocol DI throughout.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import uuid

from services.webhook_orchestrator.models import (
    DeliveryAttempt,
    DeliveryStatus,
    DeliveryStorePort,
    EventStorePort,
    EventType,
    InMemoryDeliveryStore,
    InMemoryEventStore,
    WebhookEvent,
)
from services.webhook_orchestrator.subscription_manager import SubscriptionManager


@dataclass
class EventPublisher:
    """Publishes webhook events with idempotency and fan-out delivery setup.

    Idempotency: if idempotency_key is non-empty and an event with that key
    already exists, the existing event is returned (no duplicate delivery).
    """

    event_store: EventStorePort
    delivery_store: DeliveryStorePort
    subscription_manager: SubscriptionManager

    def __init__(
        self,
        event_store: EventStorePort | None = None,
        delivery_store: DeliveryStorePort | None = None,
        subscription_manager: SubscriptionManager | None = None,
    ) -> None:
        self.event_store: EventStorePort = event_store or InMemoryEventStore()
        self.delivery_store: DeliveryStorePort = delivery_store or InMemoryDeliveryStore()
        self.subscription_manager: SubscriptionManager = (
            subscription_manager or SubscriptionManager()
        )

    def publish(
        self,
        event_type: EventType,
        payload: dict,
        source_service: str,
        idempotency_key: str = "",
    ) -> WebhookEvent:
        """Publish an event and create PENDING delivery attempts for all matching subs.

        Idempotency: if idempotency_key is non-empty and already exists, returns
        the existing event without creating new delivery attempts.
        """
        if idempotency_key:
            existing = self.event_store.get_by_idempotency_key(idempotency_key)
            if existing is not None:
                return existing

        event = WebhookEvent(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            payload=payload,
            idempotency_key=idempotency_key,
            source_service=source_service,
            created_at=datetime.now(UTC),
        )
        self.event_store.save(event)

        matching_subs = self.subscription_manager.get_matching_subscriptions(event_type)
        for sub in matching_subs:
            attempt = DeliveryAttempt(
                attempt_id=str(uuid.uuid4()),
                event_id=event.event_id,
                subscription_id=sub.subscription_id,
                status=DeliveryStatus.PENDING,
                http_status=None,
                attempt_number=1,
                response_body="",
                attempted_at=datetime.now(UTC),
                next_retry_at=None,
            )
            self.delivery_store.save(attempt)

        return event

    def get_event(self, event_id: str) -> WebhookEvent | None:
        """Retrieve an event by ID."""
        return self.event_store.get(event_id)

    def list_events(self, event_type_str: str = "", limit: int = 50) -> list[WebhookEvent]:
        """List events, optionally filtered by event type string."""
        if event_type_str:
            try:
                event_type = EventType(event_type_str)
            except ValueError:
                return []
            return self.event_store.list_by_type(event_type, limit)

        # No filter — return all events across all types
        all_events: list[WebhookEvent] = []
        for et in EventType:
            all_events.extend(self.event_store.list_by_type(et, limit))
        # Deduplicate and cap
        seen: set[str] = set()
        result: list[WebhookEvent] = []
        for e in all_events:
            if e.event_id not in seen:
                seen.add(e.event_id)
                result.append(e)
            if len(result) >= limit:
                break
        return result
