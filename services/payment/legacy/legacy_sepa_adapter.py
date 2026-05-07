"""
legacy_sepa_adapter.py — LegacySepaAdapter implements PaymentRailPort (REWRITE-3).

Semantic rewrite of CreateOutgoingTransactionsService (sepa-service).
Transport dropped per ADR-025 §15-16:
  - GCP Bifrost XML (requestToGCPProcessing / initTransaction)
  - DWH payment gRPC microservice (getByNostroAccount)
  - Redis cron / NestJS EventEmitter (syncTransactions, needsApprovalHandler)
  - TypeORM (TransactionEntity / FiatPaymentEntity)

Upstream TS method → PaymentRailPort mapping:
  initTransaction()            → submit_payment(intent)  [stored as PENDING]
  approveTransaction()         → advance_to(SUBMITTED)   [folded into submit confirm]
  fetchTransactionStatus()     → get_payment_status()
  syncTransactions() @Cron     → DROP (pull-on-demand in-memory)
  needsApprovalHandler() @Cron → DROP (approval folded into submit phase)

State machine: PENDING → SUBMITTED → SETTLED / REJECTED / CANCELLED
  Illegal transitions raise SepaApplicationError(code="invalid_state_transition").

Canon: ADR-025 §15-16 + services.payment.payment_port + SESSION-2026-05-07-WAVE-C
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
import re
import secrets
from typing import Literal

from pydantic import BaseModel

from services.payment.payment_port import (
    PaymentIntent,
    PaymentRail,
    PaymentResult,
    PaymentStatus,
)

# ── Config ────────────────────────────────────────────────────────────────────

_SEPA_RAILS: frozenset[PaymentRail] = frozenset({PaymentRail.SEPA_CT, PaymentRail.SEPA_INSTANT})
_SCT_INST_MAX_EUR: Decimal = Decimal("100000.00")
_SEPA_REFERENCE_MAX_LEN: int = 140  # ISO 20022 / SEPA rulebook


# ── Validation helpers ────────────────────────────────────────────────────────


def _validate_iban(iban: str) -> bool:
    """Return True if IBAN passes ISO 13616 mod-97 check."""
    clean = iban.replace(" ", "").upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", clean):
        return False
    rearranged = clean[4:] + clean[:4]
    numeric = "".join(str(ord(c) - 55) if c.isalpha() else c for c in rearranged)
    return int(numeric) % 97 == 1


def _validate_bic(bic: str) -> bool:
    """Return True if BIC matches SWIFT standard (8 or 11 alphanum chars)."""
    clean = bic.strip().upper()
    return bool(re.fullmatch(r"[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?", clean))


# ── Internal state ────────────────────────────────────────────────────────────


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


class SepaPayment(BaseModel, frozen=True):
    """Internal domain record for an in-flight SEPA payment."""

    payment_id: str
    idempotency_key: str
    customer_id: str
    debtor_iban: str
    creditor_iban: str
    creditor_bic: str | None
    amount: Decimal
    currency: str
    reference: str
    scheme: Literal["SCT", "SCT_INST"]
    status: SepaPaymentStatus
    created_at: datetime

    model_config = {"arbitrary_types_allowed": True}


# ── Error ─────────────────────────────────────────────────────────────────────


class SepaApplicationError(Exception):
    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


# ── Adapter ───────────────────────────────────────────────────────────────────


class LegacySepaAdapter:
    """
    PaymentRailPort implementation — SEPA CT + SCT_INST (REWRITE-3).

    In-memory store keyed by idempotency_key (dedup) and payment_id (lookup).
    Not durable or concurrency-safe; acceptable for dev/test.
    Production: replace with Modulr SEPA adapter (ModulrPaymentAdapter) or ClearBank.
    """

    def __init__(self) -> None:
        self._by_idempotency: dict[str, SepaPayment] = {}
        self._by_payment_id: dict[str, SepaPayment] = {}

    # ── PaymentRailPort ───────────────────────────────────────────────────────

    def submit_payment(self, intent: PaymentIntent) -> PaymentResult:
        if intent.rail not in _SEPA_RAILS:
            raise SepaApplicationError(
                f"LegacySepaAdapter handles only SEPA rails, got {intent.rail}",
                code="unsupported_rail",
            )

        if intent.idempotency_key in self._by_idempotency:
            return self._to_result(self._by_idempotency[intent.idempotency_key])

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

        if len(intent.reference) > _SEPA_REFERENCE_MAX_LEN:
            raise SepaApplicationError(
                f"Reference exceeds SEPA max {_SEPA_REFERENCE_MAX_LEN} chars",
                code="reference_too_long",
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

        customer_id = intent.metadata.get("customer_id", intent.debtor_account.account_holder_name)
        payment_id = f"sepa-{secrets.token_hex(8)}"
        now = datetime.now(UTC)
        payment = SepaPayment(
            payment_id=payment_id,
            idempotency_key=intent.idempotency_key,
            customer_id=str(customer_id),
            debtor_iban=debtor_iban,
            creditor_iban=creditor_iban,
            creditor_bic=creditor_bic,
            amount=intent.amount,
            currency=intent.currency,
            reference=intent.reference,
            scheme=scheme,
            status=SepaPaymentStatus.PENDING,
            created_at=now,
        )
        self._by_idempotency[intent.idempotency_key] = payment
        self._by_payment_id[payment_id] = payment
        return self._to_result(payment)

    def get_payment_status(self, provider_payment_id: str) -> PaymentResult:
        payment = self._by_payment_id.get(provider_payment_id)
        if payment is None:
            raise SepaApplicationError(
                f"Payment not found: {provider_payment_id!r}",
                code="payment_not_found",
            )
        return self._to_result(payment)

    def health_check(self) -> bool:
        return True

    # ── Extra (beyond port) ────────────────────────────────────────────────────

    def list_payments(
        self,
        *,
        customer_id: str | None = None,
        status: SepaPaymentStatus | None = None,
        scheme: Literal["SCT", "SCT_INST"] | None = None,
    ) -> list[SepaPayment]:
        results = list(self._by_payment_id.values())
        if customer_id is not None:
            results = [p for p in results if p.customer_id == customer_id]
        if status is not None:
            results = [p for p in results if p.status == status]
        if scheme is not None:
            results = [p for p in results if p.scheme == scheme]
        return results

    def advance_to(self, payment_id: str, new_status: SepaPaymentStatus) -> SepaPayment:
        """Drive state machine — used to simulate bank confirmations in tests."""
        payment = self._by_payment_id.get(payment_id)
        if payment is None:
            raise SepaApplicationError(
                f"Payment not found: {payment_id!r}", code="payment_not_found"
            )
        if new_status not in _VALID_TRANSITIONS[payment.status]:
            raise SepaApplicationError(
                f"Illegal transition: {payment.status} → {new_status}",
                code="invalid_state_transition",
            )
        updated = payment.model_copy(update={"status": new_status})
        self._by_payment_id[payment_id] = updated
        self._by_idempotency[payment.idempotency_key] = updated
        return updated

    # ── Internal ───────────────────────────────────────────────────────────────

    def _to_result(self, payment: SepaPayment) -> PaymentResult:
        rail = PaymentRail.SEPA_INSTANT if payment.scheme == "SCT_INST" else PaymentRail.SEPA_CT
        return PaymentResult(
            idempotency_key=payment.idempotency_key,
            provider_payment_id=payment.payment_id,
            status=_TO_PAYMENT_STATUS[payment.status],
            rail=rail,
            amount=payment.amount,
            currency=payment.currency,
            submitted_at=payment.created_at,
        )
