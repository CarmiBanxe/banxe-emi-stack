"""
tests/test_webhook_orchestrator/test_subscription_manager.py — SubscriptionManager tests
IL-WHO-01 | Phase 28 | banxe-emi-stack

20 tests: subscribe (HTTPS only), non-HTTPS raises ValueError, pause (ACTIVE→PAUSED),
delete always HITL_REQUIRED, get/list, get_matching_subscriptions filters by
event_type and ACTIVE status, paused subs not returned.
"""

from __future__ import annotations

import pytest

from services.webhook_orchestrator.models import (
    EventType,
    InMemorySubscriptionStore,
    SubscriptionStatus,
)
from services.webhook_orchestrator.subscription_manager import SubscriptionManager


def make_manager() -> SubscriptionManager:
    return SubscriptionManager(store=InMemorySubscriptionStore())


class TestSubscribe:
    def test_subscribe_returns_subscription(self) -> None:
        mgr = make_manager()
        sub = mgr.subscribe("owner-1", "https://example.com/hook", [EventType.PAYMENT_CREATED])
        assert sub.subscription_id is not None
        assert sub.owner_id == "owner-1"
        assert sub.status == SubscriptionStatus.ACTIVE

    def test_subscribe_https_only(self) -> None:
        mgr = make_manager()
        sub = mgr.subscribe("owner-1", "https://secure.example.com/hook", [EventType.KYC_COMPLETED])
        assert sub.url == "https://secure.example.com/hook"

    def test_subscribe_http_raises_value_error(self) -> None:
        mgr = make_manager()
        with pytest.raises(ValueError, match="HTTPS"):
            mgr.subscribe("owner-1", "http://insecure.com/hook", [EventType.PAYMENT_CREATED])

    def test_subscribe_no_scheme_raises_value_error(self) -> None:
        mgr = make_manager()
        with pytest.raises(ValueError):
            mgr.subscribe("owner-1", "insecure.com/hook", [EventType.PAYMENT_CREATED])

    def test_subscribe_generates_secret(self) -> None:
        mgr = make_manager()
        sub = mgr.subscribe("owner-1", "https://example.com/hook", [EventType.PAYMENT_CREATED])
        assert len(sub.secret) == 32

    def test_subscribe_stores_event_types(self) -> None:
        mgr = make_manager()
        sub = mgr.subscribe(
            "owner-1",
            "https://example.com/hook",
            [EventType.PAYMENT_CREATED, EventType.KYC_COMPLETED],
        )
        assert EventType.PAYMENT_CREATED in sub.event_types
        assert EventType.KYC_COMPLETED in sub.event_types

    def test_subscribe_with_description(self) -> None:
        mgr = make_manager()
        sub = mgr.subscribe(
            "owner-1",
            "https://example.com/hook",
            [EventType.PAYMENT_CREATED],
            description="Payment events",
        )
        assert sub.description == "Payment events"

    def test_subscribe_persists_to_store(self) -> None:
        mgr = make_manager()
        sub = mgr.subscribe("owner-1", "https://example.com/hook", [EventType.PAYMENT_CREATED])
        retrieved = mgr.get(sub.subscription_id)
        assert retrieved == sub

    def test_subscribe_ftp_raises_value_error(self) -> None:
        mgr = make_manager()
        with pytest.raises(ValueError):
            mgr.subscribe("owner-1", "ftp://example.com/hook", [EventType.PAYMENT_CREATED])


class TestPause:
    def test_pause_active_subscription(self) -> None:
        mgr = make_manager()
        sub = mgr.subscribe("owner-1", "https://example.com/hook", [EventType.PAYMENT_CREATED])
        paused = mgr.pause(sub.subscription_id)
        assert paused.status == SubscriptionStatus.PAUSED

    def test_pause_updates_store(self) -> None:
        mgr = make_manager()
        sub = mgr.subscribe("owner-1", "https://example.com/hook", [EventType.PAYMENT_CREATED])
        mgr.pause(sub.subscription_id)
        retrieved = mgr.get(sub.subscription_id)
        assert retrieved is not None
        assert retrieved.status == SubscriptionStatus.PAUSED

    def test_pause_missing_raises_value_error(self) -> None:
        mgr = make_manager()
        with pytest.raises(ValueError, match="not found"):
            mgr.pause("non-existent-id")

    def test_pause_already_paused_raises_value_error(self) -> None:
        mgr = make_manager()
        sub = mgr.subscribe("owner-1", "https://example.com/hook", [EventType.PAYMENT_CREATED])
        mgr.pause(sub.subscription_id)
        with pytest.raises(ValueError, match="not ACTIVE"):
            mgr.pause(sub.subscription_id)


class TestDelete:
    def test_delete_returns_hitl_required(self) -> None:
        mgr = make_manager()
        result = mgr.delete("sub-1", "admin-user")
        assert result["status"] == "HITL_REQUIRED"

    def test_delete_includes_subscription_id(self) -> None:
        mgr = make_manager()
        result = mgr.delete("sub-abc", "admin-user")
        assert result["subscription_id"] == "sub-abc"

    def test_delete_never_auto_deletes(self) -> None:
        mgr = make_manager()
        sub = mgr.subscribe("owner-1", "https://example.com/hook", [EventType.PAYMENT_CREATED])
        mgr.delete(sub.subscription_id, "admin")
        # Subscription still exists — no auto-deletion
        assert mgr.get(sub.subscription_id) is not None


class TestGetAndList:
    def test_get_existing(self) -> None:
        mgr = make_manager()
        sub = mgr.subscribe("owner-1", "https://example.com/hook", [EventType.PAYMENT_CREATED])
        found = mgr.get(sub.subscription_id)
        assert found == sub

    def test_get_missing_returns_none(self) -> None:
        mgr = make_manager()
        assert mgr.get("missing") is None

    def test_list_subscriptions_by_owner(self) -> None:
        mgr = make_manager()
        mgr.subscribe("owner-1", "https://a.example.com/hook", [EventType.PAYMENT_CREATED])
        mgr.subscribe("owner-1", "https://b.example.com/hook", [EventType.KYC_COMPLETED])
        mgr.subscribe("owner-2", "https://c.example.com/hook", [EventType.PAYMENT_CREATED])
        result = mgr.list_subscriptions("owner-1")
        assert len(result) == 2


class TestGetMatchingSubscriptions:
    def test_returns_active_matching_subs(self) -> None:
        mgr = make_manager()
        mgr.subscribe("owner-1", "https://a.example.com/hook", [EventType.PAYMENT_CREATED])
        result = mgr.get_matching_subscriptions(EventType.PAYMENT_CREATED)
        assert len(result) == 1

    def test_paused_subs_not_returned(self) -> None:
        mgr = make_manager()
        sub = mgr.subscribe("owner-1", "https://a.example.com/hook", [EventType.PAYMENT_CREATED])
        mgr.pause(sub.subscription_id)
        result = mgr.get_matching_subscriptions(EventType.PAYMENT_CREATED)
        assert len(result) == 0

    def test_different_event_type_not_returned(self) -> None:
        mgr = make_manager()
        mgr.subscribe("owner-1", "https://a.example.com/hook", [EventType.KYC_COMPLETED])
        result = mgr.get_matching_subscriptions(EventType.PAYMENT_CREATED)
        assert len(result) == 0

    def test_multiple_subs_multiple_results(self) -> None:
        mgr = make_manager()
        mgr.subscribe("owner-1", "https://a.example.com/hook", [EventType.PAYMENT_CREATED])
        mgr.subscribe("owner-2", "https://b.example.com/hook", [EventType.PAYMENT_CREATED])
        result = mgr.get_matching_subscriptions(EventType.PAYMENT_CREATED)
        assert len(result) == 2
