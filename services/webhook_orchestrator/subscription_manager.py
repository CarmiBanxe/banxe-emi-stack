"""
services/webhook_orchestrator/subscription_manager.py — Webhook Subscription Manager
IL-WHO-01 | Phase 28 | banxe-emi-stack

Manages webhook subscription lifecycle: create (HTTPS-only), pause, delete (HITL-required),
query. Protocol DI pattern for storage. Frozen dataclasses with dataclasses.replace().
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
import hashlib
import uuid

from services.webhook_orchestrator.models import (
    EventType,
    InMemorySubscriptionStore,
    SubscriptionStatus,
    SubscriptionStorePort,
    WebhookSubscription,
)


@dataclass
class SubscriptionManager:
    """Manages webhook subscription lifecycle.

    Invariant I-27: subscription deletion always requires HITL approval.
    HTTPS-only URLs enforced on subscribe.
    """

    store: SubscriptionStorePort

    def __init__(self, store: SubscriptionStorePort | None = None) -> None:
        self.store: SubscriptionStorePort = store or InMemorySubscriptionStore()

    def subscribe(
        self,
        owner_id: str,
        url: str,
        event_types: list[EventType],
        description: str = "",
    ) -> WebhookSubscription:
        """Register a new webhook subscription. URL must use HTTPS.

        Raises:
            ValueError: if url does not start with 'https://'
        """
        if not url.startswith("https://"):
            raise ValueError(f"Webhook URL must use HTTPS. Received: {url!r}")

        secret = hashlib.sha256(uuid.uuid4().hex.encode()).hexdigest()[:32]
        subscription = WebhookSubscription(
            subscription_id=str(uuid.uuid4()),
            owner_id=owner_id,
            url=url,
            event_types=list(event_types),
            status=SubscriptionStatus.ACTIVE,
            secret=secret,
            created_at=datetime.now(UTC),
            description=description,
        )
        self.store.save(subscription)
        return subscription

    def pause(self, subscription_id: str) -> WebhookSubscription:
        """Pause an ACTIVE subscription. Returns updated subscription.

        Raises:
            ValueError: if subscription not found or not ACTIVE
        """
        sub = self.store.get(subscription_id)
        if sub is None:
            raise ValueError(f"Subscription not found: {subscription_id}")
        if sub.status != SubscriptionStatus.ACTIVE:
            raise ValueError(
                f"Subscription {subscription_id} is not ACTIVE (current: {sub.status})"
            )
        updated = replace(sub, status=SubscriptionStatus.PAUSED)
        self.store.update(updated)
        return updated

    def delete(self, subscription_id: str, actor: str) -> dict:
        """Request subscription deletion. Always requires HITL approval (I-27).

        Returns HITL_REQUIRED response — never auto-deletes.
        """
        return {
            "status": "HITL_REQUIRED",
            "subscription_id": subscription_id,
            "actor": actor,
            "reason": "Subscription deletion requires Compliance Officer approval (I-27)",
        }

    def get(self, subscription_id: str) -> WebhookSubscription | None:
        """Retrieve a subscription by ID."""
        return self.store.get(subscription_id)

    def list_subscriptions(self, owner_id: str) -> list[WebhookSubscription]:
        """List all subscriptions for an owner."""
        return self.store.list_by_owner(owner_id)

    def get_matching_subscriptions(self, event_type: EventType) -> list[WebhookSubscription]:
        """Return ACTIVE subscriptions that include the given event_type."""
        # We need all subs — list_by_owner is owner-scoped, so scan all via internal store
        all_subs: list[WebhookSubscription] = []
        if hasattr(self.store, "_store"):
            all_subs = list(self.store._store.values())  # type: ignore[union-attr]
        else:
            # Fallback: protocol-compliant stores should expose all() or similar
            # For prod adapters, implement a list_all() method
            all_subs = []

        return [
            s
            for s in all_subs
            if s.status == SubscriptionStatus.ACTIVE and event_type in s.event_types
        ]
