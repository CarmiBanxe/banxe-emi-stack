"""
tests/test_webhook_orchestrator/test_delivery_engine.py — DeliveryEngine tests
IL-WHO-01 | Phase 28 | banxe-emi-stack

18 tests: deliver (stub succeeds, http_status=200), circuit OPEN → skip delivery,
schedule_retry (attempt<6 → new attempt with next delay), attempt==6 → None (dead letter),
get_retry_delay schedule, successful delivery resets failures.
"""

from __future__ import annotations

from datetime import UTC, datetime

from services.webhook_orchestrator.delivery_engine import (
    MAX_ATTEMPTS,
    RETRY_SCHEDULE,
    DeliveryEngine,
)
from services.webhook_orchestrator.models import (
    CircuitState,
    DeliveryAttempt,
    DeliveryStatus,
    EventType,
    InMemoryCircuitBreakerStore,
    InMemoryDeliveryStore,
    SubscriptionStatus,
    WebhookEvent,
    WebhookSubscription,
)

NOW = datetime(2026, 4, 17, 12, 0, 0, tzinfo=UTC)


def make_subscription(sub_id: str = "sub-1") -> WebhookSubscription:
    return WebhookSubscription(
        subscription_id=sub_id,
        owner_id="owner-1",
        url="https://example.com/hook",
        event_types=[EventType.PAYMENT_CREATED],
        status=SubscriptionStatus.ACTIVE,
        secret="abc123",
        created_at=NOW,
    )


def make_event(event_id: str = "evt-1") -> WebhookEvent:
    return WebhookEvent(
        event_id=event_id,
        event_type=EventType.PAYMENT_CREATED,
        payload={},
        idempotency_key="",
        source_service="svc",
        created_at=NOW,
    )


def make_attempt(attempt_id: str = "att-1", attempt_number: int = 1) -> DeliveryAttempt:
    return DeliveryAttempt(
        attempt_id=attempt_id,
        event_id="evt-1",
        subscription_id="sub-1",
        status=DeliveryStatus.PENDING,
        http_status=None,
        attempt_number=attempt_number,
        response_body="",
        attempted_at=NOW,
    )


def make_engine() -> tuple[DeliveryEngine, InMemoryDeliveryStore, InMemoryCircuitBreakerStore]:
    delivery_store = InMemoryDeliveryStore()
    circuit_store = InMemoryCircuitBreakerStore()
    engine = DeliveryEngine(delivery_store=delivery_store, circuit_store=circuit_store)
    return engine, delivery_store, circuit_store


class TestDeliver:
    def test_deliver_succeeds_in_stub(self) -> None:
        engine, delivery_store, _ = make_engine()
        attempt = make_attempt()
        delivery_store.save(attempt)
        result = engine.deliver(attempt, make_subscription(), make_event())
        assert result.status == DeliveryStatus.DELIVERED

    def test_deliver_returns_200_in_stub(self) -> None:
        engine, delivery_store, _ = make_engine()
        attempt = make_attempt()
        delivery_store.save(attempt)
        result = engine.deliver(attempt, make_subscription(), make_event())
        assert result.http_status == 200

    def test_deliver_updates_store(self) -> None:
        engine, delivery_store, _ = make_engine()
        attempt = make_attempt()
        delivery_store.save(attempt)
        engine.deliver(attempt, make_subscription(), make_event())
        stored = delivery_store.get("att-1")
        assert stored is not None
        assert stored.status == DeliveryStatus.DELIVERED

    def test_deliver_circuit_open_returns_failed(self) -> None:
        engine, delivery_store, circuit_store = make_engine()
        circuit_store.set_state("sub-1", CircuitState.OPEN)
        attempt = make_attempt()
        delivery_store.save(attempt)
        result = engine.deliver(attempt, make_subscription(), make_event())
        assert result.status == DeliveryStatus.FAILED

    def test_deliver_circuit_open_skips_http_call(self) -> None:
        engine, delivery_store, circuit_store = make_engine()
        circuit_store.set_state("sub-1", CircuitState.OPEN)
        attempt = make_attempt()
        delivery_store.save(attempt)
        result = engine.deliver(attempt, make_subscription(), make_event())
        assert result.http_status is None

    def test_deliver_circuit_open_message_in_body(self) -> None:
        engine, delivery_store, circuit_store = make_engine()
        circuit_store.set_state("sub-1", CircuitState.OPEN)
        attempt = make_attempt()
        delivery_store.save(attempt)
        result = engine.deliver(attempt, make_subscription(), make_event())
        assert "Circuit breaker OPEN" in result.response_body

    def test_deliver_success_resets_circuit_failures(self) -> None:
        engine, delivery_store, circuit_store = make_engine()
        circuit_store.increment_failures("sub-1")
        circuit_store.increment_failures("sub-1")
        attempt = make_attempt()
        delivery_store.save(attempt)
        engine.deliver(attempt, make_subscription(), make_event())
        # After reset, incrementing starts from 0
        count = circuit_store.increment_failures("sub-1")
        assert count == 1

    def test_deliver_closed_circuit_succeeds(self) -> None:
        engine, delivery_store, circuit_store = make_engine()
        circuit_store.set_state("sub-1", CircuitState.CLOSED)
        attempt = make_attempt()
        delivery_store.save(attempt)
        result = engine.deliver(attempt, make_subscription(), make_event())
        assert result.status == DeliveryStatus.DELIVERED

    def test_deliver_half_open_circuit_succeeds(self) -> None:
        engine, delivery_store, circuit_store = make_engine()
        circuit_store.set_state("sub-1", CircuitState.HALF_OPEN)
        attempt = make_attempt()
        delivery_store.save(attempt)
        result = engine.deliver(attempt, make_subscription(), make_event())
        assert result.status == DeliveryStatus.DELIVERED


class TestScheduleRetry:
    def test_retry_before_max_creates_new_attempt(self) -> None:
        engine, delivery_store, _ = make_engine()
        attempt = make_attempt(attempt_number=1)
        delivery_store.save(attempt)
        new_attempt = engine.schedule_retry(attempt)
        assert new_attempt is not None
        assert new_attempt.attempt_number == 2

    def test_retry_at_max_returns_none(self) -> None:
        engine, delivery_store, _ = make_engine()
        attempt = make_attempt(attempt_number=MAX_ATTEMPTS)
        delivery_store.save(attempt)
        result = engine.schedule_retry(attempt)
        assert result is None

    def test_retry_new_attempt_is_retrying_status(self) -> None:
        engine, delivery_store, _ = make_engine()
        attempt = make_attempt(attempt_number=2)
        delivery_store.save(attempt)
        new_attempt = engine.schedule_retry(attempt)
        assert new_attempt is not None
        assert new_attempt.status == DeliveryStatus.RETRYING

    def test_retry_new_attempt_has_next_retry_at(self) -> None:
        engine, delivery_store, _ = make_engine()
        attempt = make_attempt(attempt_number=1)
        delivery_store.save(attempt)
        new_attempt = engine.schedule_retry(attempt)
        assert new_attempt is not None
        assert new_attempt.next_retry_at is not None

    def test_retry_stores_new_attempt(self) -> None:
        engine, delivery_store, _ = make_engine()
        attempt = make_attempt(attempt_number=1)
        delivery_store.save(attempt)
        new_attempt = engine.schedule_retry(attempt)
        assert new_attempt is not None
        stored = delivery_store.get(new_attempt.attempt_id)
        assert stored is not None

    def test_retry_attempt_5_creates_attempt_6(self) -> None:
        engine, delivery_store, _ = make_engine()
        attempt = make_attempt(attempt_number=5)
        delivery_store.save(attempt)
        new_attempt = engine.schedule_retry(attempt)
        assert new_attempt is not None
        assert new_attempt.attempt_number == 6

    def test_retry_attempt_6_returns_none_dead_letter(self) -> None:
        engine, delivery_store, _ = make_engine()
        attempt = make_attempt(attempt_number=6)
        delivery_store.save(attempt)
        result = engine.schedule_retry(attempt)
        assert result is None


class TestGetRetryDelay:
    def test_schedule_values(self) -> None:
        engine, _, _ = make_engine()
        assert engine.get_retry_delay(1) == 1
        assert engine.get_retry_delay(2) == 5
        assert engine.get_retry_delay(3) == 30
        assert engine.get_retry_delay(4) == 300
        assert engine.get_retry_delay(5) == 1800
        assert engine.get_retry_delay(6) == 7200

    def test_retry_schedule_has_6_entries(self) -> None:
        assert len(RETRY_SCHEDULE) == 6

    def test_max_attempts_is_6(self) -> None:
        assert MAX_ATTEMPTS == 6
