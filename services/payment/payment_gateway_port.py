"""
services/payment/payment_gateway_port.py
PaymentGatewayPort Protocol — hexagonal interface for payment gateways (IL-PAY-02).

Adapters: Hyperswitch (production), InMemoryGateway (tests).
Supports full lifecycle: authorize → capture → settle → refund.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol
from uuid import uuid4

from services.payment.payment_models import TransactionStatus


@dataclass(frozen=True)
class GatewayResponse:
    """Immutable response from payment gateway."""

    gateway_reference: str
    status: TransactionStatus
    amount: Decimal  # I-01
    currency: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    error_code: str | None = None
    error_message: str | None = None


class PaymentGatewayPort(Protocol):
    """Hexagonal port for payment gateway adapters (Hyperswitch, Stripe, etc.)."""

    def authorize(
        self,
        transaction_id: str,
        amount: Decimal,
        currency: str,
        idempotency_key: str,
    ) -> GatewayResponse:
        """Request authorization hold for the given amount."""
        ...

    def capture(
        self,
        transaction_id: str,
        gateway_reference: str,
        amount: Decimal,
    ) -> GatewayResponse:
        """Capture a previously authorized payment."""
        ...

    def refund(
        self,
        transaction_id: str,
        gateway_reference: str,
        amount: Decimal,
    ) -> GatewayResponse:
        """Refund a settled payment (partial or full)."""
        ...

    def get_status(self, gateway_reference: str) -> GatewayResponse:
        """Query current status of a gateway transaction."""
        ...


class InMemoryGateway:
    """In-memory stub implementing PaymentGatewayPort for unit tests."""

    def __init__(self) -> None:
        self._transactions: dict[str, GatewayResponse] = {}
        self._idempotency_map: dict[str, GatewayResponse] = {}
        self._fail_next: bool = False
        self._block_jurisdictions: frozenset[str] = frozenset()

    def set_fail_next(self, fail: bool = True) -> None:
        """Configure next call to return FAILED status."""
        self._fail_next = fail

    def authorize(
        self,
        transaction_id: str,
        amount: Decimal,
        currency: str,
        idempotency_key: str,
    ) -> GatewayResponse:
        # Idempotency: return cached response for duplicate key.
        if idempotency_key in self._idempotency_map:
            return self._idempotency_map[idempotency_key]

        if self._fail_next:
            self._fail_next = False
            resp = GatewayResponse(
                gateway_reference=f"gw-{uuid4().hex[:12]}",
                status=TransactionStatus.FAILED,
                amount=amount,
                currency=currency,
                error_code="DECLINED",
                error_message="Authorization declined by issuer",
            )
            self._idempotency_map[idempotency_key] = resp
            return resp

        ref = f"gw-{uuid4().hex[:12]}"
        resp = GatewayResponse(
            gateway_reference=ref,
            status=TransactionStatus.AUTHORIZED,
            amount=amount,
            currency=currency,
        )
        self._transactions[ref] = resp
        self._idempotency_map[idempotency_key] = resp
        return resp

    def capture(
        self,
        transaction_id: str,
        gateway_reference: str,
        amount: Decimal,
    ) -> GatewayResponse:
        existing = self._transactions.get(gateway_reference)
        if existing is None:
            return GatewayResponse(
                gateway_reference=gateway_reference,
                status=TransactionStatus.FAILED,
                amount=amount,
                currency="GBP",
                error_code="NOT_FOUND",
                error_message="Gateway reference not found",
            )
        resp = GatewayResponse(
            gateway_reference=gateway_reference,
            status=TransactionStatus.CAPTURED,
            amount=amount,
            currency=existing.currency,
        )
        self._transactions[gateway_reference] = resp
        return resp

    def refund(
        self,
        transaction_id: str,
        gateway_reference: str,
        amount: Decimal,
    ) -> GatewayResponse:
        existing = self._transactions.get(gateway_reference)
        if existing is None:
            return GatewayResponse(
                gateway_reference=gateway_reference,
                status=TransactionStatus.FAILED,
                amount=amount,
                currency="GBP",
                error_code="NOT_FOUND",
                error_message="Gateway reference not found",
            )
        resp = GatewayResponse(
            gateway_reference=gateway_reference,
            status=TransactionStatus.REFUNDED,
            amount=amount,
            currency=existing.currency,
        )
        self._transactions[gateway_reference] = resp
        return resp

    def get_status(self, gateway_reference: str) -> GatewayResponse:
        existing = self._transactions.get(gateway_reference)
        if existing is None:
            return GatewayResponse(
                gateway_reference=gateway_reference,
                status=TransactionStatus.FAILED,
                amount=Decimal("0"),
                currency="GBP",
                error_code="NOT_FOUND",
                error_message="Gateway reference not found",
            )
        return existing
