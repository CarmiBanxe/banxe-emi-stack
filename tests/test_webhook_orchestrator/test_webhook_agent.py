"""
tests/test_webhook_orchestrator/test_webhook_agent.py — WebhookAgent tests
IL-WHO-01 | Phase 28 | banxe-emi-stack

16 tests: subscribe (valid/invalid URL), publish_event, delivery_status,
retry_dlq, list_events filtered/unfiltered.
"""

from __future__ import annotations

import pytest

from services.webhook_orchestrator.models import DeliveryStatus
from services.webhook_orchestrator.webhook_agent import WebhookAgent


def make_agent() -> WebhookAgent:
    return WebhookAgent()


class TestSubscribe:
    def test_subscribe_returns_dict_with_subscription_id(self) -> None:
        agent = make_agent()
        result = agent.subscribe("owner-1", "https://example.com/hook", ["PAYMENT_CREATED"])
        assert "subscription_id" in result
        assert result["subscription_id"] is not None

    def test_subscribe_returns_active_status(self) -> None:
        agent = make_agent()
        result = agent.subscribe("owner-1", "https://example.com/hook", ["PAYMENT_CREATED"])
        assert result["status"] == "ACTIVE"

    def test_subscribe_invalid_url_raises(self) -> None:
        agent = make_agent()
        with pytest.raises(ValueError):
            agent.subscribe("owner-1", "http://insecure.com/hook", ["PAYMENT_CREATED"])

    def test_subscribe_invalid_event_type_raises(self) -> None:
        agent = make_agent()
        with pytest.raises(ValueError):
            agent.subscribe("owner-1", "https://example.com/hook", ["INVALID_TYPE"])

    def test_subscribe_multiple_event_types(self) -> None:
        agent = make_agent()
        result = agent.subscribe(
            "owner-1",
            "https://example.com/hook",
            ["PAYMENT_CREATED", "KYC_COMPLETED"],
        )
        assert len(result["event_types"]) == 2

    def test_subscribe_with_description(self) -> None:
        agent = make_agent()
        result = agent.subscribe(
            "owner-1", "https://example.com/hook", ["PAYMENT_CREATED"], description="My webhooks"
        )
        assert result["description"] == "My webhooks"


class TestPublishEvent:
    def test_publish_returns_event_id(self) -> None:
        agent = make_agent()
        result = agent.publish_event("PAYMENT_CREATED", {"ref": "pay-1"}, "payment-service")
        assert "event_id" in result

    def test_publish_no_subscriptions_zero_attempts(self) -> None:
        agent = make_agent()
        result = agent.publish_event("PAYMENT_CREATED", {}, "payment-service")
        assert result["delivery_attempt_count"] == 0

    def test_publish_with_subscription_creates_attempt(self) -> None:
        agent = make_agent()
        agent.subscribe("owner-1", "https://example.com/hook", ["PAYMENT_CREATED"])
        result = agent.publish_event("PAYMENT_CREATED", {}, "payment-service")
        assert result["delivery_attempt_count"] == 1

    def test_publish_idempotency_dedup(self) -> None:
        agent = make_agent()
        result1 = agent.publish_event("PAYMENT_CREATED", {}, "svc", idempotency_key="ikey-x")
        result2 = agent.publish_event("PAYMENT_CREATED", {}, "svc", idempotency_key="ikey-x")
        assert result1["event_id"] == result2["event_id"]

    def test_publish_returns_event_type(self) -> None:
        agent = make_agent()
        result = agent.publish_event("KYC_COMPLETED", {}, "kyc-service")
        assert result["event_type"] == "KYC_COMPLETED"


class TestDeliveryStatus:
    def test_delivery_status_returns_event_id(self) -> None:
        agent = make_agent()
        pub_result = agent.publish_event("PAYMENT_CREATED", {}, "svc")
        status = agent.get_delivery_status(pub_result["event_id"])
        assert status["event_id"] == pub_result["event_id"]

    def test_delivery_status_empty_deliveries(self) -> None:
        agent = make_agent()
        pub_result = agent.publish_event("PAYMENT_CREATED", {}, "svc")
        status = agent.get_delivery_status(pub_result["event_id"])
        assert status["deliveries"] == []

    def test_delivery_status_includes_attempt_info(self) -> None:
        agent = make_agent()
        agent.subscribe("owner-1", "https://example.com/hook", ["PAYMENT_CREATED"])
        pub_result = agent.publish_event("PAYMENT_CREATED", {}, "svc")
        status = agent.get_delivery_status(pub_result["event_id"])
        assert len(status["deliveries"]) == 1
        assert "status" in status["deliveries"][0]


class TestRetryDlq:
    def test_retry_dlq_creates_new_pending(self) -> None:
        agent = make_agent()
        # Enqueue a dead letter manually
        from datetime import UTC, datetime

        from services.webhook_orchestrator.models import DeliveryAttempt

        store = agent.event_publisher.delivery_store
        dlq_attempt = DeliveryAttempt(
            attempt_id="dlq-1",
            event_id="evt-1",
            subscription_id="sub-1",
            status=DeliveryStatus.DEAD_LETTER,
            http_status=None,
            attempt_number=6,
            response_body="",
            attempted_at=datetime.now(UTC),
        )
        store.save(dlq_attempt)
        result = agent.retry_dlq_item("dlq-1")
        assert result["status"] == "PENDING"
        assert result["attempt_number"] == 1


class TestListEvents:
    def test_list_events_empty(self) -> None:
        agent = make_agent()
        result = agent.list_events()
        assert result["count"] == 0

    def test_list_events_returns_published(self) -> None:
        agent = make_agent()
        agent.publish_event("PAYMENT_CREATED", {}, "svc")
        agent.publish_event("PAYMENT_CREATED", {}, "svc")
        result = agent.list_events(event_type_str="PAYMENT_CREATED")
        assert result["count"] == 2

    def test_list_events_no_filter_returns_all(self) -> None:
        agent = make_agent()
        agent.publish_event("PAYMENT_CREATED", {}, "svc")
        agent.publish_event("KYC_COMPLETED", {}, "svc")
        result = agent.list_events()
        assert result["count"] == 2
