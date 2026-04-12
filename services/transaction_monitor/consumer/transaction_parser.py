"""
services/transaction_monitor/consumer/transaction_parser.py — Transaction Parser
IL-RTM-01 | banxe-emi-stack

Parses raw event payloads from RabbitMQ/Redis into TransactionEvent Pydantic models.
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from services.transaction_monitor.models.transaction import (
    RawEventPayload,
    TransactionEvent,
    TransactionType,
)

logger = logging.getLogger("banxe.transaction_monitor.parser")


class ParseError(Exception):
    """Raised when a raw event cannot be parsed into TransactionEvent."""


class TransactionParser:
    """Parses raw event dicts into TransactionEvent objects.

    Monetary amounts are parsed as Decimal (I-01).
    Invalid amounts raise ParseError immediately.
    """

    def parse(self, payload: dict[str, Any]) -> TransactionEvent:
        """Parse a raw event dict into a TransactionEvent.

        Raises:
            ParseError: If required fields are missing or amount is invalid.
        """
        try:
            amount_raw = payload.get("amount")
            if amount_raw is None:
                raise ParseError("Missing required field: amount")
            try:
                amount = Decimal(str(amount_raw))
            except InvalidOperation as e:
                raise ParseError(f"Invalid amount value: {amount_raw!r}") from e

            if amount <= 0:
                raise ParseError(f"Amount must be positive, got: {amount}")

            transaction_id = payload.get("transaction_id") or payload.get("id")
            if not transaction_id:
                raise ParseError("Missing required field: transaction_id or id")

            sender_id = payload.get("sender_id") or payload.get("customer_id")
            if not sender_id:
                raise ParseError("Missing required field: sender_id or customer_id")

            tx_type_raw = payload.get("transaction_type", "payment")
            try:
                tx_type = TransactionType(tx_type_raw)
            except ValueError:
                tx_type = TransactionType.PAYMENT
                logger.warning("Unknown transaction type '%s', defaulting to PAYMENT", tx_type_raw)

            timestamp_raw = payload.get("timestamp")
            if timestamp_raw:
                if isinstance(timestamp_raw, str):
                    timestamp = datetime.fromisoformat(timestamp_raw.replace("Z", "+00:00"))
                elif isinstance(timestamp_raw, datetime):
                    timestamp = timestamp_raw
                else:
                    timestamp = datetime.utcnow()
            else:
                timestamp = datetime.utcnow()

            # Parse customer avg if provided
            avg_raw = payload.get("customer_avg_amount")
            customer_avg = Decimal(str(avg_raw)) if avg_raw is not None else None

            return TransactionEvent(
                transaction_id=str(transaction_id),
                timestamp=timestamp,
                amount=amount,
                currency=payload.get("currency", "GBP"),
                sender_id=str(sender_id),
                receiver_id=payload.get("receiver_id"),
                transaction_type=tx_type,
                sender_jurisdiction=payload.get("sender_jurisdiction", "GB"),
                receiver_jurisdiction=payload.get("receiver_jurisdiction"),
                sender_risk_level=payload.get("sender_risk_level", "standard"),
                channel=payload.get("channel", "api"),
                metadata=payload.get("metadata", {}),
                customer_avg_amount=customer_avg,
            )
        except ParseError:
            raise
        except Exception as exc:
            raise ParseError(f"Failed to parse event: {exc}") from exc

    def parse_raw(self, raw: RawEventPayload) -> TransactionEvent:
        """Parse a RawEventPayload wrapper."""
        return self.parse(raw.payload)
