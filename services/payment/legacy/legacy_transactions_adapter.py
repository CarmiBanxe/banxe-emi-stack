"""
legacy_transactions_adapter.py — LegacyTransactionsAdapter implements PaymentRailPort (REWRITE-1).

Semantic rewrite of payment-transaction.service.ts (banxe-transactions).
Transport dropped per ADR-025 §15-16:
  - TypeORM (CashTransactionEntity / FiatPaymentEntity)
  - Redis cache read-through
  - NestJS DI decorators

Upstream TS method → Python mapping:
  parse(transaction, sendFromService, ...)  → _resolve_status() + get_payment_status()
  resolveBasePayment()                      → _to_result() (PaymentResult field population)
  resolveBaseBalances()                     → TransactionAuditRecord (NEVER in PaymentResult)

Primary port method: get_payment_status() — status lookup + audit emission.
submit_payment() is a minimal PENDING store for port completeness.

Canon: ADR-025 §15-16 + services.payment.payment_port + SESSION-2026-05-07-WAVE-C
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import secrets
from typing import Literal

from pydantic import BaseModel

from services.payment.payment_port import (
    PaymentDirection,
    PaymentIntent,
    PaymentRail,
    PaymentResult,
    PaymentStatus,
)
from services.shared.errors import BanxeLegacyAdapterError

# ── Status mapping (parse() semantic) ─────────────────────────────────────────

_TX_STATUS_MAP: dict[str, PaymentStatus] = {
    "INITIATED": PaymentStatus.PENDING,
    "PENDING": PaymentStatus.PENDING,
    "PROCESSING": PaymentStatus.PROCESSING,
    "IN_PROGRESS": PaymentStatus.PROCESSING,
    "APPROVE_REQUEST": PaymentStatus.PROCESSING,
    "COMPLETED": PaymentStatus.COMPLETED,
    "SETTLED": PaymentStatus.COMPLETED,
    "FAILED": PaymentStatus.FAILED,
    "REJECTED": PaymentStatus.FAILED,
    "RETURNED": PaymentStatus.RETURNED,
    "CANCELLED": PaymentStatus.CANCELLED,
    "CANCELED": PaymentStatus.CANCELLED,
}

_AuditEventType = Literal["SUBMITTED", "STATUS_CHANGED", "SETTLED", "FAILED", "RETURNED"]


# ── Domain models ─────────────────────────────────────────────────────────────


class TransactionRecord(BaseModel, frozen=True):
    """Internal domain record — shadows CashTransactionEntity (TypeORM DROP)."""

    transaction_id: str
    idempotency_key: str
    status: PaymentStatus
    rail: PaymentRail
    direction: PaymentDirection
    amount: Decimal
    currency: str
    submitted_at: datetime
    settled_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None
    raw_status: str = ""

    model_config = {"arbitrary_types_allowed": True}


class TransactionAuditRecord(BaseModel, frozen=True):
    """
    Audit mapping of resolveBaseBalances() — SEPARATE from PaymentResult (I-24).

    Captures pre/post status transition events; never folded into the port return value.
    In production: persisted to ClickHouse append-only table (Wave D).
    """

    transaction_id: str
    event_type: _AuditEventType
    amount: Decimal
    currency: str
    status_from: PaymentStatus | None
    status_to: PaymentStatus
    occurred_at: datetime

    model_config = {"arbitrary_types_allowed": True}


# ── Error ─────────────────────────────────────────────────────────────────────


class TransactionApplicationError(BanxeLegacyAdapterError):
    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message, code=code)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _resolve_status(raw: str) -> PaymentStatus:
    """Map raw TS status string → PaymentStatus (parse()/resolveBasePayment() semantic)."""
    mapped = _TX_STATUS_MAP.get(raw.upper())
    if mapped is None:
        raise TransactionApplicationError(
            f"Unknown transaction status: {raw!r}",
            code="unknown_status",
        )
    return mapped


def _audit_event_for(status: PaymentStatus) -> _AuditEventType:
    """Map resolved status to audit event type for TransactionAuditRecord."""
    if status == PaymentStatus.COMPLETED:
        return "SETTLED"
    if status == PaymentStatus.FAILED:
        return "FAILED"
    if status == PaymentStatus.RETURNED:
        return "RETURNED"
    if status == PaymentStatus.PENDING:
        return "SUBMITTED"
    return "STATUS_CHANGED"


# ── Adapter ───────────────────────────────────────────────────────────────────


class LegacyTransactionsAdapter:
    """
    PaymentRailPort implementation — transaction status lookup + audit (REWRITE-1).

    In-memory store keyed by transaction_id (lookup) and idempotency_key (dedup).
    Not durable or concurrency-safe; acceptable for dev/test.
    Production: replace with real provider adapter + ClickHouse audit sink (Wave D).
    """

    def __init__(self) -> None:
        self._by_transaction_id: dict[str, TransactionRecord] = {}
        self._by_idempotency: dict[str, TransactionRecord] = {}
        self._audit_log: list[TransactionAuditRecord] = []

    # ── PaymentRailPort ───────────────────────────────────────────────────────

    def submit_payment(self, intent: PaymentIntent) -> PaymentResult:
        """Minimal PENDING store — port completeness; not the primary REWRITE-1 focus."""
        if intent.idempotency_key in self._by_idempotency:
            return self._to_result(self._by_idempotency[intent.idempotency_key])
        transaction_id = f"txn-{secrets.token_hex(8)}"
        record = TransactionRecord(
            transaction_id=transaction_id,
            idempotency_key=intent.idempotency_key,
            status=PaymentStatus.PENDING,
            rail=intent.rail,
            direction=intent.direction,
            amount=intent.amount,
            currency=intent.currency,
            submitted_at=datetime.now(UTC),
            raw_status="INITIATED",
        )
        self._store(record)
        self._emit_audit(record, event_type="SUBMITTED", status_from=None)
        return self._to_result(record)

    def get_payment_status(self, provider_payment_id: str) -> PaymentResult:
        """
        Resolve current status — maps parse() + resolveBasePayment() semantics.
        Raises TransactionApplicationError(code='transaction_not_found') on miss.
        """
        record = self._by_transaction_id.get(provider_payment_id)
        if record is None:
            raise TransactionApplicationError(
                f"Transaction not found: {provider_payment_id!r}",
                code="transaction_not_found",
            )
        return self._to_result(record)

    def health(self) -> bool:
        return True

    # ── Extra (beyond port) ───────────────────────────────────────────────────

    def register_external_transaction(
        self,
        *,
        transaction_id: str,
        idempotency_key: str,
        raw_status: str,
        rail: PaymentRail,
        direction: PaymentDirection,
        amount: Decimal,
        currency: str,
        submitted_at: datetime,
        settled_at: datetime | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> TransactionRecord:
        """
        Ingest a transaction from an external source (webhook / reconciliation).
        Maps resolveBasePayment(): converts raw TS status → PaymentStatus domain value.
        """
        mapped_status = _resolve_status(raw_status)
        record = TransactionRecord(
            transaction_id=transaction_id,
            idempotency_key=idempotency_key,
            status=mapped_status,
            rail=rail,
            direction=direction,
            amount=amount,
            currency=currency,
            submitted_at=submitted_at,
            settled_at=settled_at,
            error_code=error_code,
            error_message=error_message,
            raw_status=raw_status,
        )
        self._store(record)
        self._emit_audit(record, event_type=_audit_event_for(mapped_status), status_from=None)
        return record

    def advance_status(
        self,
        transaction_id: str,
        raw_status: str,
        *,
        settled_at: datetime | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> TransactionRecord:
        """Drive status forward — used to simulate provider callbacks in tests."""
        existing = self._by_transaction_id.get(transaction_id)
        if existing is None:
            raise TransactionApplicationError(
                f"Transaction not found: {transaction_id!r}",
                code="transaction_not_found",
            )
        new_status = _resolve_status(raw_status)
        updated = existing.model_copy(
            update={
                "status": new_status,
                "raw_status": raw_status,
                "settled_at": settled_at,
                "error_code": error_code,
                "error_message": error_message,
            }
        )
        self._store(updated)
        self._emit_audit(
            updated, event_type=_audit_event_for(new_status), status_from=existing.status
        )
        return updated

    def collect_audit_records(self) -> list[TransactionAuditRecord]:
        """Return accumulated audit trail — maps resolveBaseBalances() concern (I-24)."""
        return list(self._audit_log)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _store(self, record: TransactionRecord) -> None:
        self._by_transaction_id[record.transaction_id] = record
        self._by_idempotency[record.idempotency_key] = record

    def _emit_audit(
        self,
        record: TransactionRecord,
        *,
        event_type: _AuditEventType,
        status_from: PaymentStatus | None,
    ) -> None:
        self._audit_log.append(
            TransactionAuditRecord(
                transaction_id=record.transaction_id,
                event_type=event_type,
                amount=record.amount,
                currency=record.currency,
                status_from=status_from,
                status_to=record.status,
                occurred_at=datetime.now(UTC),
            )
        )

    def _to_result(self, record: TransactionRecord) -> PaymentResult:
        return PaymentResult(
            idempotency_key=record.idempotency_key,
            provider_payment_id=record.transaction_id,
            status=record.status,
            rail=record.rail,
            amount=record.amount,
            currency=record.currency,
            submitted_at=record.submitted_at,
            error_code=record.error_code,
            error_message=record.error_message,
            estimated_settlement=record.settled_at,
        )
