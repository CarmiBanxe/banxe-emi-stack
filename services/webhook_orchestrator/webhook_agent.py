"""
services/webhook_orchestrator/webhook_agent.py — Webhook Orchestrator Agent
IL-WHO-01 | Phase 28 | banxe-emi-stack

High-level agent facade for webhook orchestration. Wires subscription manager,
event publisher, delivery engine, signature engine, and dead letter queue.
Autonomy L2 for all operations; L4 HITL for subscription deletion (I-27).
"""

from __future__ import annotations

from dataclasses import dataclass

from services.webhook_orchestrator.dead_letter_queue import DeadLetterQueue
from services.webhook_orchestrator.delivery_engine import DeliveryEngine
from services.webhook_orchestrator.event_publisher import EventPublisher
from services.webhook_orchestrator.models import (
    EventType,
    InMemoryCircuitBreakerStore,
    InMemoryDeliveryStore,
    InMemoryEventStore,
    InMemorySubscriptionStore,
)
from services.webhook_orchestrator.signature_engine import SignatureEngine
from services.webhook_orchestrator.subscription_manager import SubscriptionManager


@dataclass
class WebhookAgent:
    """Orchestrates webhook subscription, publishing, delivery, and DLQ management.

    Autonomy: L2 (subscribe, publish, deliver, retry). L4 HITL for deletion (I-27).
    """

    subscription_manager: SubscriptionManager
    event_publisher: EventPublisher
    delivery_engine: DeliveryEngine
    signature_engine: SignatureEngine
    dlq: DeadLetterQueue

    def __init__(self) -> None:
        sub_store = InMemorySubscriptionStore()
        event_store = InMemoryEventStore()
        delivery_store = InMemoryDeliveryStore()
        circuit_store = InMemoryCircuitBreakerStore()

        self.subscription_manager = SubscriptionManager(store=sub_store)
        self.event_publisher = EventPublisher(
            event_store=event_store,
            delivery_store=delivery_store,
            subscription_manager=self.subscription_manager,
        )
        self.delivery_engine = DeliveryEngine(
            delivery_store=delivery_store,
            circuit_store=circuit_store,
        )
        self.signature_engine = SignatureEngine()
        self.dlq = DeadLetterQueue(delivery_store=delivery_store)

    def subscribe(
        self,
        owner_id: str,
        url: str,
        event_types_str: list[str],
        description: str = "",
    ) -> dict:
        """Register a new webhook subscription. URL must use HTTPS.

        Returns subscription dict with subscription_id and status.
        """
        event_types = [EventType(et) for et in event_types_str]
        sub = self.subscription_manager.subscribe(
            owner_id=owner_id,
            url=url,
            event_types=event_types,
            description=description,
        )
        return {
            "subscription_id": sub.subscription_id,
            "owner_id": sub.owner_id,
            "url": sub.url,
            "event_types": [et.value for et in sub.event_types],
            "status": sub.status.value,
            "description": sub.description,
            "created_at": sub.created_at.isoformat(),
        }

    def publish_event(
        self,
        event_type_str: str,
        payload: dict,
        source_service: str,
        idempotency_key: str = "",
    ) -> dict:
        """Publish a webhook event and create delivery attempts.

        Returns event dict with delivery_attempt_count.
        """
        event_type = EventType(event_type_str)
        event = self.event_publisher.publish(
            event_type=event_type,
            payload=payload,
            source_service=source_service,
            idempotency_key=idempotency_key,
        )
        deliveries = self.event_publisher.delivery_store.list_by_event(event.event_id)
        return {
            "event_id": event.event_id,
            "event_type": event.event_type.value,
            "source_service": event.source_service,
            "idempotency_key": event.idempotency_key,
            "created_at": event.created_at.isoformat(),
            "delivery_attempt_count": len(deliveries),
        }

    def get_delivery_status(self, event_id: str) -> dict:
        """Return all delivery attempts for a given event_id."""
        deliveries = self.event_publisher.delivery_store.list_by_event(event_id)
        return {
            "event_id": event_id,
            "deliveries": [
                {
                    "attempt_id": d.attempt_id,
                    "subscription_id": d.subscription_id,
                    "status": d.status.value,
                    "http_status": d.http_status,
                    "attempt_number": d.attempt_number,
                    "attempted_at": d.attempted_at.isoformat(),
                }
                for d in deliveries
            ],
        }

    def retry_dlq_item(self, attempt_id: str) -> dict:
        """Retry a dead-lettered delivery attempt. Creates new PENDING attempt.

        Old DLQ record remains (append-only, I-24).
        """
        new_attempt = self.dlq.retry_from_dlq(attempt_id)
        return {
            "new_attempt_id": new_attempt.attempt_id,
            "event_id": new_attempt.event_id,
            "subscription_id": new_attempt.subscription_id,
            "status": new_attempt.status.value,
            "attempt_number": new_attempt.attempt_number,
        }

    def list_events(self, event_type_str: str = "", limit: int = 50) -> dict:
        """List published events, optionally filtered by event type."""
        events = self.event_publisher.list_events(event_type_str=event_type_str, limit=limit)
        return {
            "count": len(events),
            "events": [
                {
                    "event_id": e.event_id,
                    "event_type": e.event_type.value,
                    "source_service": e.source_service,
                    "idempotency_key": e.idempotency_key,
                    "created_at": e.created_at.isoformat(),
                }
                for e in events
            ],
        }
