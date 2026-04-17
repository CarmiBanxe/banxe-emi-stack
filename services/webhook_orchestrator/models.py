"""
services/webhook_orchestrator/models.py — Webhook Orchestrator domain models
IL-WHO-01 | Phase 28 | banxe-emi-stack

Domain models, enums, protocols, and InMemory stubs for the webhook orchestrator.
Protocol DI pattern throughout. Frozen dataclasses with dataclasses.replace() for mutations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol
import uuid

# ── Enums ──────────────────────────────────────────────────────────────────


class EventType(str, Enum):
    """All webhook event types emitted by Banxe EMI services."""

    PAYMENT_CREATED = "PAYMENT_CREATED"
    PAYMENT_COMPLETED = "PAYMENT_COMPLETED"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    CUSTOMER_CREATED = "CUSTOMER_CREATED"
    KYC_COMPLETED = "KYC_COMPLETED"
    KYC_FAILED = "KYC_FAILED"
    CARD_ISSUED = "CARD_ISSUED"
    CARD_FROZEN = "CARD_FROZEN"
    CARD_TRANSACTION = "CARD_TRANSACTION"
    LOAN_APPLIED = "LOAN_APPLIED"
    LOAN_APPROVED = "LOAN_APPROVED"
    LOAN_DECLINED = "LOAN_DECLINED"
    LOAN_DISBURSED = "LOAN_DISBURSED"
    INSURANCE_POLICY_BOUND = "INSURANCE_POLICY_BOUND"
    INSURANCE_CLAIM_FILED = "INSURANCE_CLAIM_FILED"
    INSURANCE_CLAIM_APPROVED = "INSURANCE_CLAIM_APPROVED"
    FX_EXECUTED = "FX_EXECUTED"
    COMPLIANCE_BREACH = "COMPLIANCE_BREACH"
    DOCUMENT_UPLOADED = "DOCUMENT_UPLOADED"
    SAFEGUARDING_ALERT = "SAFEGUARDING_ALERT"


class SubscriptionStatus(str, Enum):
    """Lifecycle states for a webhook subscription."""

    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    DELETED = "DELETED"


class DeliveryStatus(str, Enum):
    """Delivery attempt states."""

    PENDING = "PENDING"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    DEAD_LETTER = "DEAD_LETTER"


class CircuitState(str, Enum):
    """Circuit breaker states per subscription endpoint."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


# ── Frozen dataclasses ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class WebhookSubscription:
    """A registered webhook endpoint with HMAC signing secret."""

    subscription_id: str
    owner_id: str
    url: str
    event_types: list[EventType]
    status: SubscriptionStatus
    secret: str  # HMAC signing secret (hashed for storage)
    created_at: datetime
    description: str = ""


@dataclass(frozen=True)
class WebhookEvent:
    """An event emitted by a Banxe service for fan-out delivery."""

    event_id: str
    event_type: EventType
    payload: dict  # Structured JSON data — NOT monetary (no Decimal needed)
    idempotency_key: str
    source_service: str
    created_at: datetime


@dataclass(frozen=True)
class DeliveryAttempt:
    """A single delivery attempt for a webhook event to a subscription."""

    attempt_id: str
    event_id: str
    subscription_id: str
    status: DeliveryStatus
    http_status: int | None
    attempt_number: int
    response_body: str
    attempted_at: datetime
    next_retry_at: datetime | None = None


@dataclass(frozen=True)
class SignatureConfig:
    """HMAC signature configuration for a subscription."""

    config_id: str
    subscription_id: str
    algorithm: str  # "HMAC-SHA256"
    tolerance_seconds: int  # 300 (5 minutes)
    created_at: datetime


# ── Protocols ─────────────────────────────────────────────────────────────


class SubscriptionStorePort(Protocol):
    """Port for webhook subscription persistence."""

    def save(self, s: WebhookSubscription) -> None: ...

    def get(self, sub_id: str) -> WebhookSubscription | None: ...

    def list_by_owner(self, owner_id: str) -> list[WebhookSubscription]: ...

    def update(self, s: WebhookSubscription) -> None: ...


class EventStorePort(Protocol):
    """Port for webhook event persistence."""

    def save(self, e: WebhookEvent) -> None: ...

    def get(self, event_id: str) -> WebhookEvent | None: ...

    def list_by_type(self, event_type: EventType, limit: int = 50) -> list[WebhookEvent]: ...

    def get_by_idempotency_key(self, key: str) -> WebhookEvent | None: ...


class DeliveryStorePort(Protocol):
    """Port for delivery attempt persistence (append-only in prod — I-24)."""

    def save(self, d: DeliveryAttempt) -> None: ...

    def update(self, d: DeliveryAttempt) -> None: ...

    def list_by_event(self, event_id: str) -> list[DeliveryAttempt]: ...

    def list_failed(self, limit: int = 50) -> list[DeliveryAttempt]: ...

    def get(self, attempt_id: str) -> DeliveryAttempt | None: ...


class CircuitBreakerStorePort(Protocol):
    """Port for per-subscription circuit breaker state."""

    def get_state(self, subscription_id: str) -> CircuitState: ...

    def set_state(self, subscription_id: str, state: CircuitState) -> None: ...

    def increment_failures(self, subscription_id: str) -> int: ...

    def reset_failures(self, subscription_id: str) -> None: ...


# ── InMemory stubs ─────────────────────────────────────────────────────────


class InMemorySubscriptionStore:
    """InMemory stub for SubscriptionStorePort."""

    def __init__(self) -> None:
        self._store: dict[str, WebhookSubscription] = {}

    def save(self, s: WebhookSubscription) -> None:
        self._store[s.subscription_id] = s

    def get(self, sub_id: str) -> WebhookSubscription | None:
        return self._store.get(sub_id)

    def list_by_owner(self, owner_id: str) -> list[WebhookSubscription]:
        return [s for s in self._store.values() if s.owner_id == owner_id]

    def update(self, s: WebhookSubscription) -> None:
        self._store[s.subscription_id] = s


class InMemoryEventStore:
    """InMemory stub for EventStorePort."""

    def __init__(self) -> None:
        self._store: dict[str, WebhookEvent] = {}

    def save(self, e: WebhookEvent) -> None:
        self._store[e.event_id] = e

    def get(self, event_id: str) -> WebhookEvent | None:
        return self._store.get(event_id)

    def list_by_type(self, event_type: EventType, limit: int = 50) -> list[WebhookEvent]:
        results = [e for e in self._store.values() if e.event_type == event_type]
        return results[:limit]

    def get_by_idempotency_key(self, key: str) -> WebhookEvent | None:
        for e in self._store.values():
            if e.idempotency_key == key:
                return e
        return None


class InMemoryDeliveryStore:
    """InMemory stub for DeliveryStorePort (append-only semantics — I-24)."""

    def __init__(self) -> None:
        self._store: dict[str, DeliveryAttempt] = {}

    def save(self, d: DeliveryAttempt) -> None:
        self._store[d.attempt_id] = d

    def update(self, d: DeliveryAttempt) -> None:
        self._store[d.attempt_id] = d

    def list_by_event(self, event_id: str) -> list[DeliveryAttempt]:
        return [d for d in self._store.values() if d.event_id == event_id]

    def list_failed(self, limit: int = 50) -> list[DeliveryAttempt]:
        results = [
            d
            for d in self._store.values()
            if d.status in (DeliveryStatus.FAILED, DeliveryStatus.DEAD_LETTER)
        ]
        return results[:limit]

    def get(self, attempt_id: str) -> DeliveryAttempt | None:
        return self._store.get(attempt_id)


class InMemoryCircuitBreakerStore:
    """InMemory stub for CircuitBreakerStorePort."""

    def __init__(self) -> None:
        self._states: dict[str, CircuitState] = {}
        self._failures: dict[str, int] = {}

    def get_state(self, subscription_id: str) -> CircuitState:
        return self._states.get(subscription_id, CircuitState.CLOSED)

    def set_state(self, subscription_id: str, state: CircuitState) -> None:
        self._states[subscription_id] = state

    def increment_failures(self, subscription_id: str) -> int:
        self._failures[subscription_id] = self._failures.get(subscription_id, 0) + 1
        return self._failures[subscription_id]

    def reset_failures(self, subscription_id: str) -> None:
        self._failures[subscription_id] = 0


def _new_id() -> str:
    """Generate a new UUID string."""
    return str(uuid.uuid4())
