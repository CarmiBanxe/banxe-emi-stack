"""
services/payment/payment_processing_service.py
Core payment processing service — full lifecycle (IL-PAY-02).

Lifecycle: authorize → capture → settle → refund/chargeback
Covers S4-01 (initiation), S4-02 (auth), S4-03 (settlement), S4-05 (refund).

I-01: Decimal ONLY for money.
I-02: Blocked jurisdictions → JurisdictionBlockedError.
I-04: EDD threshold → HITLProposal (never auto-submitted).
I-24: Immutable audit trail for every state transition.
I-27: HITL for high-value payments.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Protocol
from uuid import uuid4

from services.customer_lifecycle.lifecycle_engine import BLOCKED_JURISDICTIONS
from services.payment.currency_validator import (
    requires_edd,
    requires_mlro_escalation,
    validate_amount,
    validate_currency,
)
from services.payment.payment_gateway_port import GatewayResponse, PaymentGatewayPort
from services.payment.payment_models import (
    VALID_TRANSITIONS,
    AuditEntry,
    PaymentTransaction,
    TransactionStatus,
)

# ── Errors ───────────────────────────────────────────────────────────────────


class JurisdictionBlockedError(ValueError):
    """Raised when beneficiary jurisdiction is sanctioned (I-02)."""


class InvalidTransitionError(ValueError):
    """Raised when a payment state transition is invalid."""


class DuplicateIdempotencyKeyError(ValueError):
    """Raised when an idempotency key has already been used."""


class EDDRequiredError(ValueError):
    """Raised when EDD is required but not yet approved (I-04)."""


class RefundExceedsAmountError(ValueError):
    """Raised when refund amount exceeds the captured/settled amount."""


# ── Audit Port ───────────────────────────────────────────────────────────────


class AuditPort(Protocol):
    """Port for recording immutable audit entries (I-24)."""

    def record(self, entry: AuditEntry) -> None: ...


class InMemoryAuditPort:
    """In-memory audit trail for tests."""

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []

    def record(self, entry: AuditEntry) -> None:
        self._entries.append(entry)

    @property
    def entries(self) -> list[AuditEntry]:
        return list(self._entries)


# ── HITL result types ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EDDHITLProposal:
    """Payment requires EDD review — HITL L4 (I-04, I-27)."""

    transaction_id: str
    customer_id: str
    amount: str  # Decimal as string (I-01, I-05)
    currency: str
    beneficiary_jurisdiction: str
    reason: str
    requires_approval_from: str = "MLRO"


# ── Payment Processing Service ───────────────────────────────────────────────


class PaymentProcessingService:
    """
    Core payment processing with full lifecycle management.

    Injected dependencies:
      - gateway: PaymentGatewayPort (Hyperswitch adapter / InMemory stub)
      - audit: AuditPort (ClickHouse / InMemory stub)

    All public methods enforce invariants I-01, I-02, I-04, I-24, I-27.
    """

    def __init__(
        self,
        gateway: PaymentGatewayPort,
        audit: AuditPort | None = None,
    ) -> None:
        self._gateway = gateway
        self._audit: AuditPort = audit or InMemoryAuditPort()
        self._transactions: dict[str, PaymentTransaction] = {}
        self._gateway_refs: dict[str, str] = {}  # tx_id → gateway_reference
        self._idempotency_keys: dict[str, str] = {}  # key → tx_id

    # ── Authorize ────────────────────────────────────────────────────────────

    def authorize(
        self,
        customer_id: str,
        amount: Decimal,
        currency: str,
        beneficiary_jurisdiction: str,
        idempotency_key: str | None = None,
        edd_approved: bool = False,
    ) -> PaymentTransaction | EDDHITLProposal:
        """
        Authorize a payment. First step in the lifecycle.

        Returns PaymentTransaction if authorized.
        Returns EDDHITLProposal if EDD threshold met and not pre-approved (I-04).
        Raises JurisdictionBlockedError if jurisdiction is sanctioned (I-02).
        """
        # I-01: validate amount is Decimal and positive.
        validate_amount(amount, currency)
        validate_currency(currency)

        # I-02: block sanctioned jurisdictions.
        jur = beneficiary_jurisdiction.upper()
        if jur in BLOCKED_JURISDICTIONS:
            raise JurisdictionBlockedError(
                f"Beneficiary jurisdiction {beneficiary_jurisdiction!r} is "
                "sanctioned and blocked (I-02)."
            )

        # Idempotency: return existing transaction for duplicate key.
        if idempotency_key and idempotency_key in self._idempotency_keys:
            existing_tx_id = self._idempotency_keys[idempotency_key]
            raise DuplicateIdempotencyKeyError(
                f"Idempotency key {idempotency_key!r} already used for "
                f"transaction {existing_tx_id}."
            )

        # I-04: EDD threshold check.
        if requires_edd(amount, currency) and not edd_approved:
            tx_id = f"tx-{uuid4().hex[:12]}"
            reason = (
                f"Payment of {currency} {amount} meets EDD threshold. "
                "MLRO approval required (I-04, I-27)."
            )
            if requires_mlro_escalation(amount, currency):
                reason = (
                    f"High-value payment of {currency} {amount} requires "
                    "MLRO escalation (I-04, I-27)."
                )
            return EDDHITLProposal(
                transaction_id=tx_id,
                customer_id=customer_id,
                amount=str(amount),
                currency=currency,
                beneficiary_jurisdiction=beneficiary_jurisdiction,
                reason=reason,
            )

        # Generate transaction ID and idempotency key.
        tx_id = f"tx-{uuid4().hex[:12]}"
        if idempotency_key is None:
            idempotency_key = uuid4().hex

        # Submit to gateway.
        gw_resp: GatewayResponse = self._gateway.authorize(
            transaction_id=tx_id,
            amount=amount,
            currency=currency,
            idempotency_key=idempotency_key,
        )

        status = gw_resp.status
        tx = PaymentTransaction(
            transaction_id=tx_id,
            idempotency_key=idempotency_key,
            customer_id=customer_id,
            amount=amount,
            currency=currency,
            beneficiary_jurisdiction=beneficiary_jurisdiction,
            status=status,
            reference=f"PAY-{tx_id}",
        )

        self._transactions[tx_id] = tx
        self._gateway_refs[tx_id] = gw_resp.gateway_reference
        self._idempotency_keys[idempotency_key] = tx_id

        # I-24: audit trail.
        self._record_audit(
            tx_id=tx_id,
            action="AUTHORIZE",
            old_status=None,
            new_status=status,
            amount=amount,
            currency=currency,
            actor=customer_id,
        )

        return tx

    # ── Capture ──────────────────────────────────────────────────────────────

    def capture(self, transaction_id: str) -> PaymentTransaction:
        """Capture a previously authorized payment."""
        tx = self._get_transaction(transaction_id)
        self._validate_transition(tx, TransactionStatus.CAPTURED)

        gw_ref = self._gateway_refs[transaction_id]
        gw_resp = self._gateway.capture(
            transaction_id=transaction_id,
            gateway_reference=gw_ref,
            amount=tx.amount,
        )

        new_tx = replace(tx, status=gw_resp.status)
        self._transactions[transaction_id] = new_tx

        self._record_audit(
            tx_id=transaction_id,
            action="CAPTURE",
            old_status=tx.status,
            new_status=gw_resp.status,
            amount=tx.amount,
            currency=tx.currency,
            actor="SYSTEM",
        )

        return new_tx

    # ── Settle ───────────────────────────────────────────────────────────────

    def settle(self, transaction_id: str) -> PaymentTransaction:
        """Mark a captured payment as settled."""
        tx = self._get_transaction(transaction_id)
        self._validate_transition(tx, TransactionStatus.SETTLED)

        new_tx = replace(tx, status=TransactionStatus.SETTLED)
        self._transactions[transaction_id] = new_tx

        self._record_audit(
            tx_id=transaction_id,
            action="SETTLE",
            old_status=tx.status,
            new_status=TransactionStatus.SETTLED,
            amount=tx.amount,
            currency=tx.currency,
            actor="SYSTEM",
        )

        return new_tx

    # ── Refund ───────────────────────────────────────────────────────────────

    def refund(
        self,
        transaction_id: str,
        amount: Decimal | None = None,
    ) -> PaymentTransaction:
        """
        Refund a settled payment (partial or full).

        If amount is None, refund the full remaining amount.
        Partial refunds track cumulative refunded_amount.
        """
        tx = self._get_transaction(transaction_id)

        # Determine refund amount.
        refund_amount = amount if amount is not None else (tx.amount - tx.refunded_amount)

        if not isinstance(refund_amount, Decimal):
            raise TypeError(
                f"Refund amount must be Decimal, got {type(refund_amount).__name__} (I-01)"
            )
        if refund_amount <= Decimal("0"):
            raise ValueError("Refund amount must be positive")

        total_refunded = tx.refunded_amount + refund_amount
        if total_refunded > tx.amount:
            raise RefundExceedsAmountError(
                f"Total refund {total_refunded} would exceed original amount {tx.amount}."
            )

        # Determine target status.
        is_full_refund = total_refunded == tx.amount
        target_status = (
            TransactionStatus.REFUNDED if is_full_refund
            else TransactionStatus.PARTIALLY_REFUNDED
        )

        self._validate_transition(tx, target_status)

        gw_ref = self._gateway_refs[transaction_id]
        self._gateway.refund(
            transaction_id=transaction_id,
            gateway_reference=gw_ref,
            amount=refund_amount,
        )

        new_tx = replace(
            tx,
            status=target_status,
            refunded_amount=total_refunded,
        )
        self._transactions[transaction_id] = new_tx

        self._record_audit(
            tx_id=transaction_id,
            action="REFUND",
            old_status=tx.status,
            new_status=target_status,
            amount=refund_amount,
            currency=tx.currency,
            actor="SYSTEM",
            details=f"refund_amount={refund_amount}, total_refunded={total_refunded}",
        )

        return new_tx

    # ── Query ────────────────────────────────────────────────────────────────

    def get_transaction(self, transaction_id: str) -> PaymentTransaction | None:
        """Return transaction by ID, or None if not found."""
        return self._transactions.get(transaction_id)

    # ── Private helpers ──────────────────────────────────────────────────────

    def _get_transaction(self, transaction_id: str) -> PaymentTransaction:
        tx = self._transactions.get(transaction_id)
        if tx is None:
            raise ValueError(f"Transaction {transaction_id!r} not found.")
        return tx

    def _validate_transition(
        self,
        tx: PaymentTransaction,
        target: TransactionStatus,
    ) -> None:
        allowed = VALID_TRANSITIONS.get(tx.status, frozenset())
        if target not in allowed:
            raise InvalidTransitionError(
                f"Cannot transition from {tx.status.value} to {target.value} "
                f"for transaction {tx.transaction_id}."
            )

    def _record_audit(
        self,
        *,
        tx_id: str,
        action: str,
        old_status: TransactionStatus | None,
        new_status: TransactionStatus,
        amount: Decimal,
        currency: str,
        actor: str,
        details: str = "",
    ) -> None:
        entry = AuditEntry(
            transaction_id=tx_id,
            action=action,
            old_status=old_status,
            new_status=new_status,
            amount=amount,
            currency=currency,
            actor=actor,
            details=details,
        )
        self._audit.record(entry)
