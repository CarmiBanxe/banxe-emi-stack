"""
event_bus.py — Domain Event Bus (In-Memory + RabbitMQ stub)
S17-11: Async inter-department messaging via event-driven architecture
FCA: FCA PS21/3 operational resilience — async decoupling of critical services

WHY THIS FILE EXISTS
--------------------
Banxe has 10 departments that need to communicate asynchronously:
  PaymentCompleted → Notification (confirmation) + Ledger (posting)
  KYCApproved → CustomerLifecycle (ONBOARDING→ACTIVE) + Agreement (send T&C)
  SafeguardingShortfall → MLRO (alert) + FCA (escalation chain)

RabbitMQ is already deployed on GMKtec (Midaz :3003/:3004).
This module adds a Banxe-domain event layer on top.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import Enum
import json
import logging
from typing import Any, Protocol
import uuid

logger = logging.getLogger(__name__)


# ── Event types ────────────────────────────────────────────────────────────────


class BanxeEventType(str, Enum):
    # Payment Operations
    PAYMENT_INITIATED = "payment.initiated"
    PAYMENT_COMPLETED = "payment.completed"
    PAYMENT_FAILED = "payment.failed"
    PAYMENT_FROZEN = "payment.frozen"  # AML freeze

    # KYC / Customer
    KYC_APPROVED = "kyc.approved"
    KYC_REJECTED = "kyc.rejected"
    KYC_EDD_REQUIRED = "kyc.edd_required"
    CUSTOMER_CREATED = "customer.created"
    CUSTOMER_ACTIVATED = "customer.activated"
    CUSTOMER_DORMANT = "customer.dormant"
    CUSTOMER_OFFBOARDED = "customer.offboarded"

    # AML / Compliance
    SAR_FILED = "aml.sar_filed"
    RISK_LEVEL_CHANGED = "aml.risk_level_changed"
    TRANSACTION_FLAGGED = "aml.transaction_flagged"

    # Safeguarding
    SAFEGUARDING_SHORTFALL = "safeguarding.shortfall"
    SAFEGUARDING_MATCHED = "safeguarding.matched"
    RECON_COMPLETED = "recon.completed"

    # Agreement
    AGREEMENT_CREATED = "agreement.created"
    AGREEMENT_SIGNED = "agreement.signed"

    # Reporting
    FIN060_GENERATED = "reporting.fin060_generated"
    REGDATA_SUBMITTED = "reporting.regdata_submitted"


# ── Base event ─────────────────────────────────────────────────────────────────


@dataclass
class DomainEvent:
    """
    Immutable domain event — all cross-department messages use this shape.
    Stored in ClickHouse banxe.domain_events for FCA audit trail.
    """

    event_id: str
    event_type: BanxeEventType
    source_service: str  # "payment_service", "kyc_service", etc.
    payload: dict[str, Any]
    occurred_at: datetime
    correlation_id: str | None = None  # Links related events (e.g. payment flow)
    customer_id: str | None = None

    def to_json(self) -> str:
        d = asdict(self)
        d["event_type"] = self.event_type.value
        d["occurred_at"] = self.occurred_at.isoformat()
        return json.dumps(d)

    @classmethod
    def create(
        cls,
        event_type: BanxeEventType,
        source_service: str,
        payload: dict[str, Any],
        customer_id: str | None = None,
        correlation_id: str | None = None,
    ) -> DomainEvent:
        return cls(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            source_service=source_service,
            payload=payload,
            occurred_at=datetime.now(UTC),
            customer_id=customer_id,
            correlation_id=correlation_id,
        )


# ── Handler type ───────────────────────────────────────────────────────────────

EventHandler = Callable[[DomainEvent], None]


# ── Port Protocol ──────────────────────────────────────────────────────────────


class EventBusPort(Protocol):
    def publish(self, event: DomainEvent) -> None: ...
    def subscribe(self, event_type: BanxeEventType, handler: EventHandler) -> None: ...


# ── In-memory event bus ────────────────────────────────────────────────────────


class InMemoryEventBus:
    """
    Synchronous in-memory event bus for tests and local development.
    Handlers are called immediately in the same thread.
    """

    def __init__(self) -> None:
        self._handlers: dict[BanxeEventType, list[EventHandler]] = {}
        self._published: list[DomainEvent] = []

    def subscribe(self, event_type: BanxeEventType, handler: EventHandler) -> None:
        self._handlers.setdefault(event_type, []).append(handler)
        logger.debug("Subscribed to %s: %s", event_type, handler.__name__)

    def publish(self, event: DomainEvent) -> None:
        self._published.append(event)
        logger.info(
            "Event published: %s [%s] customer=%s",
            event.event_type,
            event.event_id[:8],
            event.customer_id,
        )
        for handler in self._handlers.get(event.event_type, []):
            try:
                handler(event)
            except Exception as exc:
                logger.error(
                    "Handler %s failed for event %s: %s",
                    handler.__name__,
                    event.event_id,
                    exc,
                )

    @property
    def all_events(self) -> list[DomainEvent]:
        return list(self._published)

    def events_of_type(self, event_type: BanxeEventType) -> list[DomainEvent]:
        return [e for e in self._published if e.event_type == event_type]

    def clear(self) -> None:
        """Reset for test isolation."""
        self._published.clear()


# ── RabbitMQ event bus (production) ───────────────────────────────────────────


class RabbitMQEventBus:  # pragma: no cover
    """
    Production event bus — publishes to RabbitMQ (banxe-events exchange).
    RabbitMQ is already deployed on GMKtec (Midaz ports :3003/:3004).

    STATUS: STUB — requires RABBITMQ_URL env var.
    Topic routing: event_type value = routing key (e.g. "payment.completed")
    Exchange: banxe-events (topic)
    """

    def __init__(self, rabbitmq_url: str | None = None) -> None:
        import os

        self._url = rabbitmq_url or os.environ.get("RABBITMQ_URL", "")
        if not self._url:
            raise OSError(
                "RABBITMQ_URL not set. Set to amqp://user:pass@gmktec:5672/ "
                "to use RabbitMQ event bus."
            )

    def publish(self, event: DomainEvent) -> None:
        try:
            import pika  # type: ignore[import]
        except ImportError:
            raise ImportError("Install pika: pip install pika")

        params = pika.URLParameters(self._url)
        conn = pika.BlockingConnection(params)
        channel = conn.channel()
        channel.exchange_declare(
            exchange="banxe-events",
            exchange_type="topic",
            durable=True,
        )
        channel.basic_publish(
            exchange="banxe-events",
            routing_key=event.event_type.value,
            body=event.to_json().encode(),
            properties=pika.BasicProperties(
                delivery_mode=2,  # persistent
                content_type="application/json",
                message_id=event.event_id,
            ),
        )
        conn.close()
        logger.info("RabbitMQ published: %s [%s]", event.event_type, event.event_id[:8])

    def subscribe(self, event_type: BanxeEventType, handler: EventHandler) -> None:
        """
        Start a background pika consumer thread for one event type.

        Binds a transient queue to the banxe-events exchange with
        routing_key = event_type.value (topic pattern).
        The consumer thread is a daemon — it stops when the process exits.

        Note: for production use, prefer a dedicated consumer process or
        n8n workflow subscription rather than an in-process daemon thread.
        """
        try:
            import pika  # type: ignore[import]
        except ImportError:
            raise ImportError("Install pika: pip install pika")

        import threading

        routing_key = event_type.value

        def _consume() -> None:
            params = pika.URLParameters(self._url)
            conn = pika.BlockingConnection(params)
            channel = conn.channel()
            channel.exchange_declare(
                exchange="banxe-events",
                exchange_type="topic",
                durable=True,
            )
            result = channel.queue_declare(queue="", exclusive=True)
            queue_name = result.method.queue
            channel.queue_bind(
                exchange="banxe-events",
                queue=queue_name,
                routing_key=routing_key,
            )

            def _on_message(ch, method, props, body: bytes) -> None:  # type: ignore[no-untyped-def]
                try:
                    data = json.loads(body.decode())
                    event = DomainEvent(
                        event_id=data["event_id"],
                        event_type=BanxeEventType(data["event_type"]),
                        source_service=data["source_service"],
                        payload=data.get("payload", {}),
                        occurred_at=datetime.fromisoformat(data["occurred_at"]),
                        correlation_id=data.get("correlation_id"),
                        customer_id=data.get("customer_id"),
                    )
                    handler(event)
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                except Exception as exc:
                    logger.error("RabbitMQ handler %s failed: %s", handler.__name__, exc)
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(queue=queue_name, on_message_callback=_on_message)
            logger.info(
                "RabbitMQ consumer started: exchange=banxe-events routing_key=%s",
                routing_key,
            )
            channel.start_consuming()

        thread = threading.Thread(target=_consume, daemon=True, name=f"rmq-{routing_key}")
        thread.start()
        logger.info("RabbitMQ subscribe thread started: %s → %s", routing_key, handler.__name__)


# ── Factory ────────────────────────────────────────────────────────────────────


def get_event_bus() -> InMemoryEventBus | RabbitMQEventBus:
    import os

    backend = os.environ.get("EVENT_BUS_BACKEND", "memory")
    if backend == "rabbitmq":
        return RabbitMQEventBus()
    return InMemoryEventBus()
