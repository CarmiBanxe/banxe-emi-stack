"""
legacy_sepa_adapter.py — LegacySepaAdapter implements PaymentRailPort (REWRITE-3).

Semantic rewrite of CreateOutgoingTransactionsService (sepa-service).
Transport dropped per ADR-025 §15-16:
  - GCP Bifrost XML (requestToGCPProcessing / initTransaction)
  - DWH payment gRPC microservice (getByNostroAccount)
  - Redis cron / NestJS EventEmitter (syncTransactions, needsApprovalHandler)
  - TypeORM (TransactionEntity / FiatPaymentEntity)
  - SCA factor / VOP approval (approveTransaction SMS/TOTP auth)

Upstream TS method → PaymentRailPort mapping:
  approveTransaction(dto)        → advance_to(SUBMITTED)   [SCA dropped]
  needsApprovalHandler() @Cron   → DROP (pull-on-demand)
  syncTransactions() @Cron       → DROP (in-memory)

State machine: PENDING → SUBMITTED → SETTLED / REJECTED / CANCELLED
  PENDING → CANCELLED also allowed.
  Illegal transitions raise SepaApplicationError(code="invalid_state_transition").

Idempotency: keyed by (customer_id, reference) composite — not intent idempotency_key.
  Rationale: SEPA rulebook uniqueness is on (creditor+debtor+reference+amount);
  using (customer_id, reference) as practical surrogate.

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
    PaymentIntent,
    PaymentRail,
    PaymentResult,
    PaymentStatus,
)
from services.payment.sepa_validation import (
    SCT_INSTANT_MAX_EUR,
    validate_bic,
    validate_iban,
)
from services.shared.errors import BanxeLegacyAdapterError

# ── Constants ─────────────────────────────────────────────────────────────────

_SEPA_RAILS: frozenset[PaymentRail] = frozenset({PaymentRail.SEPA_CT, PaymentRail.SEPA_INSTANT})
_SEPA_REFERENCE_MAX_LEN: int = 140
_CREDITOR_NAME_MAX_LEN: int = 70

_SepaEventType = Literal["CREATED", "SUBMITTED", "SETTLED", "REJECTED", "CANCELLED"]

# ── Validation helpers ────────────────────────────────────────────────────────
# Canonical source is services.payment.sepa_validation (ADR-102 single source of truth).
# Back-compat aliases below preserve existing `_validate_*` / `_SCT_INST_MAX_EUR` references.
_validate_iban = validate_iban
_validate_bic = validate_bic
_SCT_INST_MAX_EUR = SCT_INSTANT_MAX_EUR


# ── State machine ─────────────────────────────────────────────────────────────


class SepaPaymentStatus(str, Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    SETTLED = "SETTLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


_VALID_TRANSITIONS: dict[SepaPaymentStatus, frozenset[SepaPaymentStatus]] = {
    SepaPaymentStatus.PENDING: frozenset(
        {SepaPaymentStatus.SUBMITTED, SepaPaymentStatus.CANCELLED}
    ),
    SepaPaymentStatus.SUBMITTED: frozenset(
        {
            SepaPaymentStatus.SETTLED,
            SepaPaymentStatus.REJECTED,
            SepaPaymentStatus.CANCELLED,
        }
    ),
    SepaPaymentStatus.SETTLED: frozenset(),
    SepaPaymentStatus.REJECTED: frozenset(),
    SepaPaymentStatus.CANCELLED: frozenset(),
}

_TO_PAYMENT_STATUS: dict[SepaPaymentStatus, PaymentStatus] = {
    SepaPaymentStatus.PENDING: PaymentStatus.PENDING,
    SepaPaymentStatus.SUBMITTED: PaymentStatus.PROCESSING,
    SepaPaymentStatus.SETTLED: PaymentStatus.COMPLETED,
    SepaPaymentStatus.REJECTED: PaymentStatus.FAILED,
    SepaPaymentStatus.CANCELLED: PaymentStatus.CANCELLED,
}


# ── Domain models ─────────────────────────────────────────────────────────────


class SepaPaymentRecord(BaseModel, frozen=True):
    """Internal domain record — shadows SEPA TransactionEntity (TypeORM DROP)."""

    payment_id: str
    idempotency_key: str
    customer_id: str
    debtor_iban: str
    creditor_iban: str
    creditor_bic: str | None
    creditor_name: str
    amount: Decimal
    currency: str
    reference: str
    scheme: Literal["SCT", "SCT_INST"]
    status: SepaPaymentStatus
    submitted_at: datetime
    settled_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None

    model_config = {"arbitrary_types_allowed": True}


class SepaAuditRecord(BaseAuditRecord, frozen=True):
    """
    Append-only audit event — I-24 compliance.

    Separate from PaymentResult; persisted to ClickHouse in Wave D.
    scheme added in Phase 5 tranche 3 for ClickHouse partitioning (SCT vs SCT_INST).
    """

    payment_id: str
    event_type: _SepaEventType  # type: ignore[assignment]
    amount: Decimal
    currency: str
    scheme: Literal["SCT", "SCT_INST"]
    status_from: SepaPaymentStatus | None  # type: ignore[assignment]
    status_to: SepaPaymentStatus  # type: ignore[assignment]


# ── Error ─────────────────────────────────────────────────────────────────────


class SepaApplicationError(BanxeLegacyAdapterError):
    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message, code=code)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _sepa_event_for(status: SepaPaymentStatus) -> _SepaEventType:
    if status == SepaPaymentStatus.SUBMITTED:
        return "SUBMITTED"
    if status == SepaPaymentStatus.SETTLED:
        return "SETTLED"
    if status == SepaPaymentStatus.REJECTED:
        return "REJECTED"
    if status == SepaPaymentStatus.CANCELLED:
        return "CANCELLED"
    return "CREATED"


# ── Adapter ───────────────────────────────────────────────────────────────────


class LegacySepaAdapter:
    """
    PaymentRailPort implementation — SEPA CT + SCT_INST (REWRITE-3).

    Idempotency keyed by (customer_id, reference) composite — SEPA rulebook surrogate.
    In-memory; not durable or concurrency-safe. Production: Modulr / ClearBank Wave D.
    """

    def __init__(self) -> None:
        self._by_payment_id: dict[str, SepaPaymentRecord] = {}
        self._by_composite_key: dict[str, SepaPaymentRecord] = {}
        self._audit_log: list[SepaAuditRecord] = []

    # ── PaymentRailPort ───────────────────────────────────────────────────────

    def submit_payment(self, intent: PaymentIntent) -> PaymentResult:
        """
        initTransaction() semantic — validate, dedup by (customer_id, reference), store PENDING.
        """
        if intent.rail not in _SEPA_RAILS:
            raise SepaApplicationError(
                f"LegacySepaAdapter handles only SEPA rails, got {intent.rail}",
                code="unsupported_rail",
            )

        customer_id = str(
            intent.metadata.get("customer_id", intent.debtor_account.account_holder_name)
        )
        composite_key = f"{customer_id}::{intent.reference}"
        if composite_key in self._by_composite_key:
            return self._to_result(self._by_composite_key[composite_key])

        debtor_iban = intent.debtor_account.iban or ""
        creditor_iban = intent.creditor_account.iban or ""

        if not debtor_iban or not _validate_iban(debtor_iban):
            raise SepaApplicationError(f"Invalid debtor IBAN: {debtor_iban!r}", code="invalid_iban")
        if not creditor_iban or not _validate_iban(creditor_iban):
            raise SepaApplicationError(
                f"Invalid creditor IBAN: {creditor_iban!r}", code="invalid_iban"
            )

        creditor_bic = intent.creditor_account.bic
        if creditor_bic and not _validate_bic(creditor_bic):
            raise SepaApplicationError(f"Invalid BIC: {creditor_bic!r}", code="invalid_bic")

        creditor_name = intent.creditor_account.account_holder_name
        if not creditor_name or not creditor_name.strip():
            raise SepaApplicationError(
                "Creditor name must not be empty", code="invalid_creditor_name"
            )
        if len(creditor_name) > _CREDITOR_NAME_MAX_LEN:
            raise SepaApplicationError(
                f"Creditor name exceeds {_CREDITOR_NAME_MAX_LEN} chars",
                code="creditor_name_too_long",
            )

        if not intent.reference or not intent.reference.strip():
            raise SepaApplicationError("Reference must not be empty", code="invalid_reference")
        if len(intent.reference) > _SEPA_REFERENCE_MAX_LEN:
            raise SepaApplicationError(
                f"Reference exceeds SEPA max {_SEPA_REFERENCE_MAX_LEN} chars",
                code="reference_too_long",
            )

        tup = intent.amount.as_tuple()
        if tup.exponent < -2:
            raise SepaApplicationError(
                f"Amount must have at most 2 decimal places, got {intent.amount}",
                code="invalid_amount_precision",
            )

        scheme: Literal["SCT", "SCT_INST"]
        if intent.rail == PaymentRail.SEPA_INSTANT:
            scheme = "SCT_INST"
            if intent.amount > _SCT_INST_MAX_EUR:
                raise SepaApplicationError(
                    f"SCT_INST amount {intent.amount} exceeds €{_SCT_INST_MAX_EUR}",
                    code="amount_exceeds_sct_inst_limit",
                )
        else:
            scheme = "SCT"

        payment_id = f"sepa-{secrets.token_hex(8)}"
        record = SepaPaymentRecord(
            payment_id=payment_id,
            idempotency_key=intent.idempotency_key,
            customer_id=customer_id,
            debtor_iban=debtor_iban,
            creditor_iban=creditor_iban,
            creditor_bic=creditor_bic,
            creditor_name=creditor_name,
            amount=intent.amount,
            currency=intent.currency,
            reference=intent.reference,
            scheme=scheme,
            status=SepaPaymentStatus.PENDING,
            submitted_at=datetime.now(UTC),
        )
        self._store(record)
        self._emit_audit(record, event_type="CREATED", status_from=None)
        return self._to_result(record)

    def get_payment_status(self, provider_payment_id: str) -> PaymentResult:
        record = self._by_payment_id.get(provider_payment_id)
        if record is None:
            raise SepaApplicationError(
                f"Payment not found: {provider_payment_id!r}",
                code="payment_not_found",
            )
        return self._to_result(record)

    def health(self) -> bool:
        return True

    # ── Extra (beyond port) ───────────────────────────────────────────────────

    def advance_to(
        self,
        payment_id: str,
        new_status: SepaPaymentStatus,
        *,
        settled_at: datetime | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> SepaPaymentRecord:
        """approveTransaction() semantic — drive state machine (SCA dropped)."""
        existing = self._by_payment_id.get(payment_id)
        if existing is None:
            raise SepaApplicationError(
                f"Payment not found: {payment_id!r}", code="payment_not_found"
            )
        assert_valid_transition(
            current=existing.status,
            target=new_status,
            transitions=_VALID_TRANSITIONS,
            adapter_error_cls=SepaApplicationError,
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
            updated, event_type=_sepa_event_for(new_status), status_from=existing.status
        )
        return updated

    def list_payments(
        self,
        *,
        customer_id: str | None = None,
        status: SepaPaymentStatus | None = None,
        scheme: Literal["SCT", "SCT_INST"] | None = None,
    ) -> list[SepaPaymentRecord]:
        """List payments with optional filters (multi-tenant isolation by customer_id)."""
        results = list(self._by_payment_id.values())
        if customer_id is not None:
            results = [p for p in results if p.customer_id == customer_id]
        if status is not None:
            results = [p for p in results if p.status == status]
        if scheme is not None:
            results = [p for p in results if p.scheme == scheme]
        return results

    def collect_audit_records(self) -> list[SepaAuditRecord]:
        """Return accumulated audit trail — I-24 append-only."""
        return list(self._audit_log)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _store(self, record: SepaPaymentRecord) -> None:
        self._by_payment_id[record.payment_id] = record
        composite = f"{record.customer_id}::{record.reference}"
        self._by_composite_key[composite] = record

    def _emit_audit(
        self,
        record: SepaPaymentRecord,
        *,
        event_type: _SepaEventType,
        status_from: SepaPaymentStatus | None,
    ) -> None:
        self._audit_log.append(
            SepaAuditRecord(
                record_id=record.payment_id,
                customer_id=record.customer_id,
                payment_id=record.payment_id,
                event_type=event_type,
                amount=record.amount,
                currency=record.currency,
                scheme=record.scheme,
                status_from=status_from,
                status_to=record.status,
                occurred_at=datetime.now(UTC),
            )
        )

    def _to_result(self, record: SepaPaymentRecord) -> PaymentResult:
        rail = PaymentRail.SEPA_INSTANT if record.scheme == "SCT_INST" else PaymentRail.SEPA_CT
        return PaymentResult(
            idempotency_key=record.idempotency_key,
            provider_payment_id=record.payment_id,
            status=_TO_PAYMENT_STATUS[record.status],
            rail=rail,
            amount=record.amount,
            currency=record.currency,
            submitted_at=record.submitted_at,
            error_code=record.error_code,
            error_message=record.error_message,
            estimated_settlement=record.settled_at,
        )
