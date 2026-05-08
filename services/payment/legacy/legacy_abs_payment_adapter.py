"""
legacy_abs_payment_adapter.py — LegacyAbsPaymentAdapter implements PaymentRailPort (REWRITE-2).

Semantic rewrite of abs-customer-payment.service.ts (banxe-fiat-backend/abs-api).
Transport dropped per ADR-025 §15-16:
  - GCP Bifrost XML gateway (requestToGCPProcessing)
  - Sequential DB counters (TypeORM)
  - NestJS EventEmitter

Upstream TS method → Python mapping:
  createOrUpdateCustomerPayment(dto) → submit_payment(intent)
  approveCustomerPayment(id, vop)   → advance_to(payment_id, AbsPaymentStatus.SUBMITTED)
  Bank ref / doc number generation  → _generate_ref() helper

Canon: ADR-025 §15-16 + services.payment.payment_port + SESSION-2026-05-07-WAVE-C
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
import secrets
from typing import Literal

from pydantic import BaseModel

from services._legacy_common.audit import BaseAuditRecord
from services._legacy_common.state_machine import assert_valid_transition
from services.payment.payment_port import (
    PaymentDirection,
    PaymentIntent,
    PaymentRail,
    PaymentResult,
    PaymentStatus,
)
from services.shared.errors import BanxeLegacyAdapterError

# ── Constants ──────────────────────────────────────────────────────────────────

_ABS_SUPPORTED_RAILS = frozenset({PaymentRail.SEPA_CT, PaymentRail.SEPA_INSTANT})
_ABS_REFERENCE_MAX_LEN = 140

_AbsEventType = Literal["CREATED", "SUBMITTED", "SETTLED", "REJECTED", "CANCELLED"]

# ── ABS payment state machine ──────────────────────────────────────────────────


class AbsPaymentStatus(str, Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    SETTLED = "SETTLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


_VALID_TRANSITIONS: dict[AbsPaymentStatus, frozenset[AbsPaymentStatus]] = {
    AbsPaymentStatus.PENDING: frozenset({AbsPaymentStatus.SUBMITTED, AbsPaymentStatus.CANCELLED}),
    AbsPaymentStatus.SUBMITTED: frozenset({AbsPaymentStatus.SETTLED, AbsPaymentStatus.REJECTED}),
    AbsPaymentStatus.SETTLED: frozenset(),
    AbsPaymentStatus.REJECTED: frozenset(),
    AbsPaymentStatus.CANCELLED: frozenset(),
}

_TO_PAYMENT_STATUS: dict[AbsPaymentStatus, PaymentStatus] = {
    AbsPaymentStatus.PENDING: PaymentStatus.PENDING,
    AbsPaymentStatus.SUBMITTED: PaymentStatus.PROCESSING,
    AbsPaymentStatus.SETTLED: PaymentStatus.COMPLETED,
    AbsPaymentStatus.REJECTED: PaymentStatus.FAILED,
    AbsPaymentStatus.CANCELLED: PaymentStatus.CANCELLED,
}


# ── Domain models ─────────────────────────────────────────────────────────────


class AbsPaymentRecord(BaseModel, frozen=True):
    """Internal domain record — shadows ABS customer payment entity (TypeORM DROP)."""

    payment_id: str
    idempotency_key: str
    customer_id: str
    debtor_account_name: str
    creditor_account_name: str
    creditor_iban: str | None
    amount: Decimal
    currency: str
    reference: str
    bank_ref: str
    rail: PaymentRail
    direction: PaymentDirection
    status: AbsPaymentStatus
    submitted_at: datetime
    settled_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None

    model_config = {"arbitrary_types_allowed": True}


class AbsAuditRecord(BaseAuditRecord, frozen=True):
    """
    Append-only audit event — I-24 compliance.

    Maps the TypeORM event emission DROP; persisted to ClickHouse in Wave D.
    NEVER folded into PaymentResult.
    """

    payment_id: str
    event_type: _AbsEventType  # type: ignore[assignment]
    amount: Decimal
    currency: str
    status_from: AbsPaymentStatus | None  # type: ignore[assignment]
    status_to: AbsPaymentStatus  # type: ignore[assignment]


# ── Error ─────────────────────────────────────────────────────────────────────


class AbsApplicationError(BanxeLegacyAdapterError):
    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message, code=code)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _generate_ref(customer_id: str) -> str:
    """Generate unique bank ref — replaces TypeORM sequential counter (ADR-025 §15-16)."""
    prefix = (customer_id[:4]).upper() if customer_id else "ABS"
    ts = datetime.now(UTC).strftime("%Y%m%d")
    token = secrets.token_hex(6)
    return f"ABS-{prefix}-{ts}-{token}"


def _abs_event_for(status: AbsPaymentStatus) -> _AbsEventType:
    """Map AbsPaymentStatus to audit event type."""
    if status == AbsPaymentStatus.SUBMITTED:
        return "SUBMITTED"
    if status == AbsPaymentStatus.SETTLED:
        return "SETTLED"
    if status == AbsPaymentStatus.REJECTED:
        return "REJECTED"
    if status == AbsPaymentStatus.CANCELLED:
        return "CANCELLED"
    return "CREATED"


# ── Adapter ───────────────────────────────────────────────────────────────────


class LegacyAbsPaymentAdapter:
    """
    PaymentRailPort implementation — ABS domain payment submit + state machine (REWRITE-2).

    In-memory store keyed by payment_id (lookup) and idempotency_key (dedup).
    Not durable or concurrency-safe; acceptable for dev/test.
    Production: replace with GCP Bifrost XML adapter + ClickHouse audit sink (Wave D).
    """

    def __init__(self) -> None:
        self._by_payment_id: dict[str, AbsPaymentRecord] = {}
        self._by_idempotency: dict[str, AbsPaymentRecord] = {}
        self._audit_log: list[AbsAuditRecord] = []

    # ── PaymentRailPort ───────────────────────────────────────────────────────

    def submit_payment(self, intent: PaymentIntent) -> PaymentResult:
        """
        createOrUpdateCustomerPayment() semantic — store PENDING, idempotent.
        Validates rail support + reference length before storing.
        """
        if intent.rail not in _ABS_SUPPORTED_RAILS:
            raise AbsApplicationError(
                f"Unsupported rail for ABS adapter: {intent.rail}",
                code="unsupported_rail",
            )
        if len(intent.reference) > _ABS_REFERENCE_MAX_LEN:
            raise AbsApplicationError(
                f"Reference exceeds {_ABS_REFERENCE_MAX_LEN} chars",
                code="reference_too_long",
            )
        if intent.idempotency_key in self._by_idempotency:
            return self._to_result(self._by_idempotency[intent.idempotency_key])

        customer_id = str(
            intent.metadata.get("customer_id", intent.debtor_account.account_holder_name)
        )
        payment_id = f"abs-{secrets.token_hex(8)}"
        bank_ref = _generate_ref(customer_id)
        record = AbsPaymentRecord(
            payment_id=payment_id,
            idempotency_key=intent.idempotency_key,
            customer_id=customer_id,
            debtor_account_name=intent.debtor_account.account_holder_name,
            creditor_account_name=intent.creditor_account.account_holder_name,
            creditor_iban=intent.creditor_account.iban,
            amount=intent.amount,
            currency=intent.currency,
            reference=intent.reference,
            bank_ref=bank_ref,
            rail=intent.rail,
            direction=intent.direction,
            status=AbsPaymentStatus.PENDING,
            submitted_at=datetime.now(UTC),
        )
        self._store(record)
        self._emit_audit(record, event_type="CREATED", status_from=None)
        return self._to_result(record)

    def get_payment_status(self, provider_payment_id: str) -> PaymentResult:
        """Fetch current status. Raises AbsApplicationError(code='payment_not_found') on miss."""
        record = self._by_payment_id.get(provider_payment_id)
        if record is None:
            raise AbsApplicationError(
                f"ABS payment not found: {provider_payment_id!r}",
                code="payment_not_found",
            )
        return self._to_result(record)

    def health(self) -> bool:
        return True

    # ── Extra (beyond port) ───────────────────────────────────────────────────

    def advance_to(
        self,
        payment_id: str,
        new_status: AbsPaymentStatus,
        *,
        settled_at: datetime | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> AbsPaymentRecord:
        """approveCustomerPayment() semantic — drive state machine forward."""
        existing = self._by_payment_id.get(payment_id)
        if existing is None:
            raise AbsApplicationError(
                f"ABS payment not found: {payment_id!r}",
                code="payment_not_found",
            )
        assert_valid_transition(
            current=existing.status,
            target=new_status,
            transitions=_VALID_TRANSITIONS,
            adapter_error_cls=AbsApplicationError,
        )
        updated = existing.model_copy(
            update={
                "status": new_status,
                "settled_at": settled_at,
                "error_code": error_code,
                "error_message": error_message,
            }
        )
        self._store(updated)
        self._emit_audit(
            updated, event_type=_abs_event_for(new_status), status_from=existing.status
        )
        return updated

    def list_payments(
        self,
        *,
        customer_id: str | None = None,
        status: AbsPaymentStatus | None = None,
    ) -> list[AbsPaymentRecord]:
        """List payments with optional filters (multi-tenant isolation by customer_id)."""
        records = list(self._by_payment_id.values())
        if customer_id is not None:
            records = [r for r in records if r.customer_id == customer_id]
        if status is not None:
            records = [r for r in records if r.status == status]
        return records

    def collect_audit_records(self) -> list[AbsAuditRecord]:
        """Return accumulated audit trail — I-24 append-only."""
        return list(self._audit_log)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _store(self, record: AbsPaymentRecord) -> None:
        self._by_payment_id[record.payment_id] = record
        self._by_idempotency[record.idempotency_key] = record

    def _emit_audit(
        self,
        record: AbsPaymentRecord,
        *,
        event_type: _AbsEventType,
        status_from: AbsPaymentStatus | None,
    ) -> None:
        self._audit_log.append(
            AbsAuditRecord(
                record_id=record.payment_id,
                customer_id=record.customer_id,
                payment_id=record.payment_id,
                event_type=event_type,
                amount=record.amount,
                currency=record.currency,
                status_from=status_from,
                status_to=record.status,
                occurred_at=datetime.now(UTC),
            )
        )

    def _to_result(self, record: AbsPaymentRecord) -> PaymentResult:
        return PaymentResult(
            idempotency_key=record.idempotency_key,
            provider_payment_id=record.payment_id,
            status=_TO_PAYMENT_STATUS[record.status],
            rail=record.rail,
            amount=record.amount,
            currency=record.currency,
            submitted_at=record.submitted_at,
            error_code=record.error_code,
            error_message=record.error_message,
            estimated_settlement=record.settled_at,
        )
