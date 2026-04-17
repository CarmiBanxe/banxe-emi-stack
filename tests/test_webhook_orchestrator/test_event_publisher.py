"""
tests/test_webhook_orchestrator/test_event_publisher.py — EventPublisher tests
IL-WHO-01 | Phase 28 | banxe-emi-stack

18 tests: publish creates event + delivery attempts, idempotency key deduplication
(second call returns same event), list_events by type, get_event,
no subscriptions = no delivery attempts, multiple subscriptions = multiple attempts.
"""

from __future__ import annotations

from services.webhook_orchestrator.event_publisher import EventPublisher
from services.webhook_orchestrator.models import (
    EventType,
    InMemoryDeliveryStore,
    InMemoryEventStore,
)
from services.webhook_orchestrator.subscription_manager import SubscriptionManager


def make_publisher() -> tuple[EventPublisher, SubscriptionManager]:
    sub_mgr = SubscriptionManager()
    delivery_store = InMemoryDeliveryStore()
    event_store = InMemoryEventStore()
    publisher = EventPublisher(
        event_store=event_store,
        delivery_store=delivery_store,
        subscription_manager=sub_mgr,
    )
    return publisher, sub_mgr


class TestPublish:
    def test_publish_creates_event(self) -> None:
        publisher, _ = make_publisher()
        event = publisher.publish(
            EventType.PAYMENT_CREATED,
            {"ref": "pay-1"},
            source_service="payment-service",
        )
        assert event.event_id is not None
        assert event.event_type == EventType.PAYMENT_CREATED

    def test_publish_stores_event(self) -> None:
        publisher, _ = make_publisher()
        event = publisher.publish(
            EventType.KYC_COMPLETED,
            {"customer_id": "cust-1"},
            source_service="kyc-service",
        )
        retrieved = publisher.get_event(event.event_id)
        assert retrieved == event

    def test_publish_no_subscriptions_no_attempts(self) -> None:
        publisher, _ = make_publisher()
        event = publisher.publish(EventType.PAYMENT_CREATED, {}, source_service="payment-service")
        deliveries = publisher.delivery_store.list_by_event(event.event_id)
        assert len(deliveries) == 0

    def test_publish_one_subscription_one_attempt(self) -> None:
        publisher, sub_mgr = make_publisher()
        sub_mgr.subscribe("owner-1", "https://a.example.com/hook", [EventType.PAYMENT_CREATED])
        event = publisher.publish(EventType.PAYMENT_CREATED, {}, source_service="payment-service")
        deliveries = publisher.delivery_store.list_by_event(event.event_id)
        assert len(deliveries) == 1

    def test_publish_multiple_subscriptions_multiple_attempts(self) -> None:
        publisher, sub_mgr = make_publisher()
        sub_mgr.subscribe("owner-1", "https://a.example.com/hook", [EventType.PAYMENT_CREATED])
        sub_mgr.subscribe("owner-2", "https://b.example.com/hook", [EventType.PAYMENT_CREATED])
        event = publisher.publish(EventType.PAYMENT_CREATED, {}, source_service="payment-service")
        deliveries = publisher.delivery_store.list_by_event(event.event_id)
        assert len(deliveries) == 2

    def test_publish_delivery_attempts_are_pending(self) -> None:
        publisher, sub_mgr = make_publisher()
        sub_mgr.subscribe("owner-1", "https://a.example.com/hook", [EventType.PAYMENT_CREATED])
        event = publisher.publish(EventType.PAYMENT_CREATED, {}, source_service="payment-service")
        from services.webhook_orchestrator.models import DeliveryStatus

        deliveries = publisher.delivery_store.list_by_event(event.event_id)
        assert all(d.status == DeliveryStatus.PENDING for d in deliveries)

    def test_publish_subscription_different_type_no_attempt(self) -> None:
        publisher, sub_mgr = make_publisher()
        sub_mgr.subscribe("owner-1", "https://a.example.com/hook", [EventType.KYC_COMPLETED])
        event = publisher.publish(EventType.PAYMENT_CREATED, {}, source_service="payment-service")
        deliveries = publisher.delivery_store.list_by_event(event.event_id)
        assert len(deliveries) == 0

    def test_publish_stores_source_service(self) -> None:
        publisher, _ = make_publisher()
        event = publisher.publish(EventType.FX_EXECUTED, {}, source_service="fx-engine")
        assert event.source_service == "fx-engine"


class TestIdempotency:
    def test_idempotency_key_deduplication(self) -> None:
        publisher, _ = make_publisher()
        event1 = publisher.publish(
            EventType.PAYMENT_CREATED, {}, source_service="svc", idempotency_key="ikey-1"
        )
        event2 = publisher.publish(
            EventType.PAYMENT_CREATED, {}, source_service="svc", idempotency_key="ikey-1"
        )
        assert event1.event_id == event2.event_id

    def test_idempotency_second_call_no_new_attempts(self) -> None:
        publisher, sub_mgr = make_publisher()
        sub_mgr.subscribe("owner-1", "https://a.example.com/hook", [EventType.PAYMENT_CREATED])
        publisher.publish(
            EventType.PAYMENT_CREATED, {}, source_service="svc", idempotency_key="ikey-2"
        )
        event2 = publisher.publish(
            EventType.PAYMENT_CREATED, {}, source_service="svc", idempotency_key="ikey-2"
        )
        # Only 1 delivery attempt (from first publish)
        deliveries = publisher.delivery_store.list_by_event(event2.event_id)
        assert len(deliveries) == 1

    def test_empty_idempotency_key_no_dedup(self) -> None:
        publisher, _ = make_publisher()
        event1 = publisher.publish(EventType.PAYMENT_CREATED, {}, source_service="svc")
        event2 = publisher.publish(EventType.PAYMENT_CREATED, {}, source_service="svc")
        assert event1.event_id != event2.event_id

    def test_different_idempotency_keys_different_events(self) -> None:
        publisher, _ = make_publisher()
        event1 = publisher.publish(
            EventType.PAYMENT_CREATED, {}, source_service="svc", idempotency_key="key-A"
        )
        event2 = publisher.publish(
            EventType.PAYMENT_CREATED, {}, source_service="svc", idempotency_key="key-B"
        )
        assert event1.event_id != event2.event_id


class TestGetAndList:
    def test_get_event_by_id(self) -> None:
        publisher, _ = make_publisher()
        event = publisher.publish(EventType.PAYMENT_CREATED, {}, source_service="svc")
        found = publisher.get_event(event.event_id)
        assert found == event

    def test_get_event_missing_returns_none(self) -> None:
        publisher, _ = make_publisher()
        assert publisher.get_event("does-not-exist") is None

    def test_list_events_by_type(self) -> None:
        publisher, _ = make_publisher()
        publisher.publish(EventType.PAYMENT_CREATED, {}, source_service="svc")
        publisher.publish(EventType.PAYMENT_CREATED, {}, source_service="svc")
        publisher.publish(EventType.KYC_COMPLETED, {}, source_service="svc")
        results = publisher.list_events(event_type_str="PAYMENT_CREATED")
        assert len(results) == 2

    def test_list_events_no_filter_returns_all(self) -> None:
        publisher, _ = make_publisher()
        publisher.publish(EventType.PAYMENT_CREATED, {}, source_service="svc")
        publisher.publish(EventType.KYC_COMPLETED, {}, source_service="svc")
        results = publisher.list_events()
        assert len(results) == 2

    def test_list_events_invalid_type_returns_empty(self) -> None:
        publisher, _ = make_publisher()
        results = publisher.list_events(event_type_str="NOT_A_REAL_EVENT")
        assert results == []

    def test_list_events_limit_respected(self) -> None:
        publisher, _ = make_publisher()
        for _ in range(5):
            publisher.publish(EventType.PAYMENT_CREATED, {}, source_service="svc")
        results = publisher.list_events(event_type_str="PAYMENT_CREATED", limit=3)
        assert len(results) == 3
