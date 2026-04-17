"""
tests/test_webhook_orchestrator/test_models.py — Models unit tests
IL-WHO-01 | Phase 28 | banxe-emi-stack

18 tests: dataclass creation, frozen enforcement, enum values, InMemory store CRUD,
idempotency key lookup, DeliveryAttempt state transitions.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from services.webhook_orchestrator.models import (
    CircuitState,
    DeliveryAttempt,
    DeliveryStatus,
    EventType,
    InMemoryCircuitBreakerStore,
    InMemoryDeliveryStore,
    InMemoryEventStore,
    InMemorySubscriptionStore,
    SignatureConfig,
    SubscriptionStatus,
    WebhookEvent,
    WebhookSubscription,
)

# ── Fixtures ───────────────────────────────────────────────────────────────

NOW = datetime(2026, 4, 17, 12, 0, 0, tzinfo=UTC)


def make_subscription(sub_id: str = "sub-1", owner_id: str = "owner-1") -> WebhookSubscription:
    return WebhookSubscription(
        subscription_id=sub_id,
        owner_id=owner_id,
        url="https://example.com/hook",
        event_types=[EventType.PAYMENT_CREATED],
        status=SubscriptionStatus.ACTIVE,
        secret="abc123",
        created_at=NOW,
        description="test",
    )


def make_event(event_id: str = "evt-1", ikey: str = "") -> WebhookEvent:
    return WebhookEvent(
        event_id=event_id,
        event_type=EventType.PAYMENT_CREATED,
        payload={"amount": "100.00"},
        idempotency_key=ikey,
        source_service="payment-service",
        created_at=NOW,
    )


def make_attempt(
    attempt_id: str = "att-1", event_id: str = "evt-1", sub_id: str = "sub-1"
) -> DeliveryAttempt:
    return DeliveryAttempt(
        attempt_id=attempt_id,
        event_id=event_id,
        subscription_id=sub_id,
        status=DeliveryStatus.PENDING,
        http_status=None,
        attempt_number=1,
        response_body="",
        attempted_at=NOW,
    )


# ── Enum tests ─────────────────────────────────────────────────────────────


class TestEventTypeEnum:
    def test_payment_created_value(self) -> None:
        assert EventType.PAYMENT_CREATED.value == "PAYMENT_CREATED"

    def test_kyc_completed_value(self) -> None:
        assert EventType.KYC_COMPLETED.value == "KYC_COMPLETED"

    def test_total_event_types(self) -> None:
        assert len(EventType) == 20

    def test_safeguarding_alert_value(self) -> None:
        assert EventType.SAFEGUARDING_ALERT.value == "SAFEGUARDING_ALERT"


class TestSubscriptionStatusEnum:
    def test_active(self) -> None:
        assert SubscriptionStatus.ACTIVE.value == "ACTIVE"

    def test_paused(self) -> None:
        assert SubscriptionStatus.PAUSED.value == "PAUSED"

    def test_deleted(self) -> None:
        assert SubscriptionStatus.DELETED.value == "DELETED"


# ── Frozen dataclass tests ─────────────────────────────────────────────────


class TestWebhookSubscriptionDataclass:
    def test_creation(self) -> None:
        sub = make_subscription()
        assert sub.subscription_id == "sub-1"
        assert sub.status == SubscriptionStatus.ACTIVE
        assert sub.url == "https://example.com/hook"

    def test_frozen_immutable(self) -> None:
        sub = make_subscription()
        with pytest.raises((AttributeError, TypeError)):
            sub.status = SubscriptionStatus.PAUSED  # type: ignore[misc]

    def test_default_description_empty(self) -> None:
        sub = WebhookSubscription(
            subscription_id="s",
            owner_id="o",
            url="https://x.com",
            event_types=[],
            status=SubscriptionStatus.ACTIVE,
            secret="s",
            created_at=NOW,
        )
        assert sub.description == ""


class TestWebhookEventDataclass:
    def test_creation(self) -> None:
        event = make_event()
        assert event.event_id == "evt-1"
        assert event.event_type == EventType.PAYMENT_CREATED
        assert event.payload == {"amount": "100.00"}

    def test_frozen_immutable(self) -> None:
        event = make_event()
        with pytest.raises((AttributeError, TypeError)):
            event.event_type = EventType.KYC_COMPLETED  # type: ignore[misc]


class TestDeliveryAttemptDataclass:
    def test_creation(self) -> None:
        attempt = make_attempt()
        assert attempt.status == DeliveryStatus.PENDING
        assert attempt.http_status is None
        assert attempt.attempt_number == 1

    def test_next_retry_at_default_none(self) -> None:
        attempt = make_attempt()
        assert attempt.next_retry_at is None

    def test_frozen_immutable(self) -> None:
        attempt = make_attempt()
        with pytest.raises((AttributeError, TypeError)):
            attempt.status = DeliveryStatus.DELIVERED  # type: ignore[misc]


class TestSignatureConfigDataclass:
    def test_creation(self) -> None:
        cfg = SignatureConfig(
            config_id="cfg-1",
            subscription_id="sub-1",
            algorithm="HMAC-SHA256",
            tolerance_seconds=300,
            created_at=NOW,
        )
        assert cfg.algorithm == "HMAC-SHA256"
        assert cfg.tolerance_seconds == 300


# ── InMemory store tests ───────────────────────────────────────────────────


class TestInMemorySubscriptionStore:
    def test_save_and_get(self) -> None:
        store = InMemorySubscriptionStore()
        sub = make_subscription()
        store.save(sub)
        assert store.get("sub-1") == sub

    def test_get_missing_returns_none(self) -> None:
        store = InMemorySubscriptionStore()
        assert store.get("nope") is None

    def test_list_by_owner(self) -> None:
        store = InMemorySubscriptionStore()
        store.save(make_subscription("sub-1", "owner-1"))
        store.save(make_subscription("sub-2", "owner-2"))
        result = store.list_by_owner("owner-1")
        assert len(result) == 1
        assert result[0].subscription_id == "sub-1"

    def test_update_replaces(self) -> None:
        from dataclasses import replace

        store = InMemorySubscriptionStore()
        sub = make_subscription()
        store.save(sub)
        updated = replace(sub, status=SubscriptionStatus.PAUSED)
        store.update(updated)
        assert store.get("sub-1").status == SubscriptionStatus.PAUSED  # type: ignore[union-attr]


class TestInMemoryEventStore:
    def test_save_and_get(self) -> None:
        store = InMemoryEventStore()
        event = make_event()
        store.save(event)
        assert store.get("evt-1") == event

    def test_list_by_type(self) -> None:
        store = InMemoryEventStore()
        store.save(make_event("evt-1"))
        store.save(make_event("evt-2"))
        result = store.list_by_type(EventType.PAYMENT_CREATED)
        assert len(result) == 2

    def test_get_by_idempotency_key(self) -> None:
        store = InMemoryEventStore()
        event = make_event("evt-1", ikey="ikey-abc")
        store.save(event)
        found = store.get_by_idempotency_key("ikey-abc")
        assert found == event

    def test_get_by_idempotency_key_missing_returns_none(self) -> None:
        store = InMemoryEventStore()
        assert store.get_by_idempotency_key("does-not-exist") is None


class TestInMemoryDeliveryStore:
    def test_save_and_get(self) -> None:
        store = InMemoryDeliveryStore()
        attempt = make_attempt()
        store.save(attempt)
        assert store.get("att-1") == attempt

    def test_list_by_event(self) -> None:
        store = InMemoryDeliveryStore()
        store.save(make_attempt("att-1", "evt-1"))
        store.save(make_attempt("att-2", "evt-1"))
        store.save(make_attempt("att-3", "evt-2"))
        result = store.list_by_event("evt-1")
        assert len(result) == 2

    def test_list_failed_returns_failed_and_dlq(self) -> None:
        from dataclasses import replace

        store = InMemoryDeliveryStore()
        failed = replace(make_attempt("att-1"), status=DeliveryStatus.FAILED)
        dlq = replace(make_attempt("att-2"), status=DeliveryStatus.DEAD_LETTER)
        ok = replace(make_attempt("att-3"), status=DeliveryStatus.DELIVERED)
        store.save(failed)
        store.save(dlq)
        store.save(ok)
        result = store.list_failed()
        assert len(result) == 2

    def test_update_replaces(self) -> None:
        from dataclasses import replace

        store = InMemoryDeliveryStore()
        attempt = make_attempt()
        store.save(attempt)
        updated = replace(attempt, status=DeliveryStatus.DELIVERED, http_status=200)
        store.update(updated)
        assert store.get("att-1").status == DeliveryStatus.DELIVERED  # type: ignore[union-attr]


class TestInMemoryCircuitBreakerStore:
    def test_default_state_closed(self) -> None:
        store = InMemoryCircuitBreakerStore()
        assert store.get_state("sub-1") == CircuitState.CLOSED

    def test_set_state(self) -> None:
        store = InMemoryCircuitBreakerStore()
        store.set_state("sub-1", CircuitState.OPEN)
        assert store.get_state("sub-1") == CircuitState.OPEN

    def test_increment_failures(self) -> None:
        store = InMemoryCircuitBreakerStore()
        count = store.increment_failures("sub-1")
        assert count == 1
        count = store.increment_failures("sub-1")
        assert count == 2

    def test_reset_failures(self) -> None:
        store = InMemoryCircuitBreakerStore()
        store.increment_failures("sub-1")
        store.reset_failures("sub-1")
        count = store.increment_failures("sub-1")
        assert count == 1
