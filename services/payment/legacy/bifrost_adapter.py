"""bifrost_adapter.py — BifrostAdapter implements PaymentRailPort (MIG-M2.5-BIF, Wave-D).

GCP Bifrost XML transport adapter (ADR-025 §15-16) — the Wave-D production transport that the
``LegacyAbsPaymentAdapter`` rewrite deferred. Implements the EXISTING ``PaymentRailPort`` (NOT a new
parallel port) and consumes the ABS state-machine (``AbsPaymentStatus``). This scaffold is
**advisory / sandbox**: it builds the outbound ``requestToGCPProcessing``-shaped XML request descriptor
and models the inbound ``handler-incoming-messages-from-gcp`` message — but makes **NO live GCP calls**,
no settlement / fund movement, and does NOT call Midaz LedgerPort. Amounts stay ``Decimal`` per the
PaymentRailPort contract (FCA I-24); minor-unit derivation for the XML uses Decimal→int (never float).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
import secrets

from services.payment.legacy.legacy_abs_payment_adapter import AbsPaymentStatus
from services.payment.payment_port import (
    PaymentIntent,
    PaymentResult,
    PaymentStatus,
)

#: Sandbox guard — Wave-D live GCP transport is NOT wired in this scaffold.
BIFROST_SANDBOX = True

#: ISO 4217 minor-unit exponents (config-as-data; GBP/EUR = 2dp).
_MINOR_UNITS: dict[str, int] = {"GBP": 2, "EUR": 2}

#: Bifrost XML status code -> ABS state-machine (consume AbsPaymentStatus; descriptive).
_BIFROST_TO_ABS: dict[str, AbsPaymentStatus] = {
    "ACCEPTED": AbsPaymentStatus.SUBMITTED,
    "PROCESSING": AbsPaymentStatus.SUBMITTED,
    "SETTLED": AbsPaymentStatus.SETTLED,
    "REJECTED": AbsPaymentStatus.REJECTED,
    "CANCELLED": AbsPaymentStatus.CANCELLED,
}

#: ABS state-machine -> PaymentRailPort PaymentStatus (for PaymentResult).
_ABS_TO_PAYMENT: dict[AbsPaymentStatus, PaymentStatus] = {
    AbsPaymentStatus.PENDING: PaymentStatus.PENDING,
    AbsPaymentStatus.SUBMITTED: PaymentStatus.PROCESSING,
    AbsPaymentStatus.SETTLED: PaymentStatus.COMPLETED,
    AbsPaymentStatus.REJECTED: PaymentStatus.FAILED,
    AbsPaymentStatus.CANCELLED: PaymentStatus.CANCELLED,
}


def to_minor_units(amount: Decimal, currency: str) -> int:
    """Decimal major units -> int minor units for the XML descriptor (never float)."""
    if not isinstance(amount, Decimal):  # I-24: Decimal only
        raise TypeError("amount must be Decimal")
    dp = _MINOR_UNITS.get(currency.upper(), 2)
    return int((amount * (Decimal(10) ** dp)).to_integral_value(rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class BifrostXmlRequest:
    """Outbound GCP Bifrost XML request descriptor (requestToGCPProcessing-shape; sandbox, not sent)."""

    message_id: str
    request_type: str  # "requestToGCPProcessing"
    provider_payment_id: str
    amount_minor: int
    currency: str
    creditor_iban: str
    reference: str
    end_to_end_id: str
    xml: str  # descriptive XML payload (sandbox)
    source: str = "sandbox-mock"


@dataclass
class BifrostInboundMessage:
    """Inbound GCP message descriptor (handler-incoming-messages-from-gcp shape; descriptive)."""

    message_id: str
    provider_payment_id: str
    bifrost_status: str
    raw: dict = field(default_factory=dict)


@dataclass
class _BifrostRecord:
    idempotency_key: str
    provider_payment_id: str
    abs_status: AbsPaymentStatus
    amount: Decimal
    currency: str
    rail: object
    submitted_at: datetime


class BifrostAdapter:
    """PaymentRailPort implementation — GCP Bifrost XML transport (Wave-D, advisory/sandbox)."""

    def __init__(self) -> None:
        self._by_idempotency: dict[str, _BifrostRecord] = {}
        self._by_payment_id: dict[str, _BifrostRecord] = {}

    # ── PaymentRailPort ────────────────────────────────────────────────────────
    def submit_payment(self, intent: PaymentIntent) -> PaymentResult:
        """Build the outbound Bifrost XML request and record PENDING (idempotent; NO live GCP call)."""
        if intent.idempotency_key in self._by_idempotency:
            return self._to_result(self._by_idempotency[intent.idempotency_key])
        provider_payment_id = f"bifrost-{secrets.token_hex(8)}"
        self.build_outbound_xml(intent, provider_payment_id)  # descriptor only; not sent (sandbox)
        record = _BifrostRecord(
            idempotency_key=intent.idempotency_key,
            provider_payment_id=provider_payment_id,
            abs_status=AbsPaymentStatus.PENDING,
            amount=intent.amount,
            currency=intent.currency,
            rail=intent.rail,
            submitted_at=datetime.now(UTC),
        )
        self._by_idempotency[intent.idempotency_key] = record
        self._by_payment_id[provider_payment_id] = record
        return self._to_result(record)

    def get_payment_status(self, provider_payment_id: str) -> PaymentResult:
        record = self._by_payment_id.get(provider_payment_id)
        if record is None:
            raise KeyError(f"bifrost payment not found: {provider_payment_id!r}")  # fail-closed
        return self._to_result(record)

    def health(self) -> bool:
        return True

    # ── Bifrost transport (advisory / sandbox) ──────────────────────────────────
    def build_outbound_xml(
        self, intent: PaymentIntent, provider_payment_id: str
    ) -> BifrostXmlRequest:
        """requestToGCPProcessing-shaped descriptor — descriptive XML, NOT transmitted (sandbox)."""
        minor = to_minor_units(intent.amount, intent.currency)
        xml = (
            f"<GCPRequest type='requestToGCPProcessing' id='{provider_payment_id}'>"
            f"<Amount minor='{minor}' ccy='{intent.currency}'/>"
            f"<Creditor iban='{intent.creditor_account.iban}'/>"
            f"<Ref>{intent.reference}</Ref></GCPRequest>"
        )
        return BifrostXmlRequest(
            message_id=f"msg-{secrets.token_hex(6)}",
            request_type="requestToGCPProcessing",
            provider_payment_id=provider_payment_id,
            amount_minor=minor,
            currency=intent.currency,
            creditor_iban=intent.creditor_account.iban,
            reference=intent.reference,
            end_to_end_id=intent.end_to_end_id,
            xml=xml,
        )

    def handle_inbound(self, message: BifrostInboundMessage) -> AbsPaymentStatus:
        """Map an inbound GCP message to an ABS state transition (descriptive; no live side effects)."""
        abs_status = _BIFROST_TO_ABS.get(message.bifrost_status.upper())
        if abs_status is None:
            raise ValueError(f"unknown bifrost status: {message.bifrost_status!r}")  # fail-closed
        record = self._by_payment_id.get(message.provider_payment_id)
        if record is not None:
            record.abs_status = abs_status
        return abs_status

    # ── helpers ─────────────────────────────────────────────────────────────────
    def _to_result(self, record: _BifrostRecord) -> PaymentResult:
        return PaymentResult(
            idempotency_key=record.idempotency_key,
            provider_payment_id=record.provider_payment_id,
            status=_ABS_TO_PAYMENT[record.abs_status],
            rail=record.rail,
            amount=record.amount,
            currency=record.currency,
            submitted_at=record.submitted_at,
        )
