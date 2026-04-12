"""
services/transaction_monitor/consumer/event_consumer.py — Event Consumer
IL-RTM-01 | banxe-emi-stack

Consumes transaction events from RabbitMQ/Redis stream and dispatches
to the risk scoring pipeline. Protocol DI for testability.
"""

from __future__ import annotations

from collections.abc import Callable
import logging
from typing import Any, Protocol, runtime_checkable

from services.transaction_monitor.consumer.transaction_parser import TransactionParser
from services.transaction_monitor.models.alert import AMLAlert
from services.transaction_monitor.models.transaction import TransactionEvent

logger = logging.getLogger("banxe.transaction_monitor.consumer")

# Type alias for score+route handler
ScoringHandler = Callable[[TransactionEvent], AMLAlert]


@runtime_checkable
class StreamPort(Protocol):
    """Interface for reading from a stream (RabbitMQ / Redis Streams)."""

    def consume(self, callback: Callable[[dict[str, Any]], None]) -> None: ...
    def stop(self) -> None: ...


class InMemoryStreamPort:
    """Test stub — processes a pre-loaded list of events synchronously."""

    def __init__(self, events: list[dict[str, Any]] | None = None) -> None:
        self._events = events or []
        self._stopped = False

    def consume(self, callback: Callable[[dict[str, Any]], None]) -> None:
        for event in self._events:
            if self._stopped:
                break
            callback(event)

    def stop(self) -> None:
        self._stopped = True


class EventConsumer:
    """Consumes events from a stream and dispatches to scoring handler.

    Each received event is:
    1. Parsed into a TransactionEvent
    2. Passed to the scoring_handler
    3. Errors are logged but do not stop consumption
    """

    def __init__(
        self,
        stream: StreamPort,
        scoring_handler: ScoringHandler,
    ) -> None:
        self._stream = stream
        self._handler = scoring_handler
        self._parser = TransactionParser()
        self._processed = 0
        self._errors = 0

    def start(self) -> None:
        """Start consuming events from the stream."""
        logger.info("Event consumer starting")
        self._stream.consume(self._on_event)

    def stop(self) -> None:
        self._stream.stop()
        logger.info(
            "Event consumer stopped. Processed: %d, Errors: %d",
            self._processed,
            self._errors,
        )

    def stats(self) -> dict[str, int]:
        return {"processed": self._processed, "errors": self._errors}

    def _on_event(self, raw: dict[str, Any]) -> None:
        """Process a single raw event."""
        try:
            event = self._parser.parse(raw)
            self._handler(event)
            self._processed += 1
        except Exception as exc:
            self._errors += 1
            logger.error(
                "Failed to process event %s: %s",
                raw.get("transaction_id", "unknown"),
                exc,
            )
