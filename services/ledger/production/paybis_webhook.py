"""PAYBIS webhook / event intake contract (Wave A, structural).

PAYBIS delivers payment/order lifecycle events via webhook/callback (SRC-05/06 structural FACT:
events paymentInitiated/paymentCompleted/Completed/Refunded/cancelled; ids requestId/
partnerOrderId/transactionId; signed request). This module models the INTAKE shape only:

  - `PaybisWebhookEvent` — parsed, immutable event mapped onto the FROZEN CryptoTransactionStatus.
  - `parse_event` — structural parse of the known latin fields (testable, no secrets).
  - signature verification is **FENCED**: the literal signature algorithm + signed fields are
    НЕИЗВЕСТНО (SRC-06 pending), so `verify_signature` raises rather than guessing.
  - **Idempotency key** = partner_order_id (fallback transaction_id) — callers MUST dedupe.

No live HTTP, no secrets, no funds. Wave B fills the literal verification once SRC-06 lands.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from services.ledger.crypto_ledger_port import CryptoLedgerError, CryptoTransactionStatus
from services.ledger.production.paybis_crypto_adapter import map_order_status


class PaybisWebhookSpecUnknownError(CryptoLedgerError):
    """Raised when a literal webhook detail (e.g. signature algorithm) is not yet specified."""

    def __init__(self, detail: str) -> None:
        super().__init__(
            f"PAYBIS webhook spec unknown (Wave A): {detail}; requires clean SRC-06 API spec.",
            code="PAYBIS_WEBHOOK_SPEC_UNKNOWN",
        )


@dataclass(frozen=True)
class PaybisWebhookEvent:
    """A parsed PAYBIS webhook event (immutable). `status` is the FROZEN-port mapped state."""

    event_type: str
    request_id: str | None
    partner_order_id: str | None
    transaction_id: str | None
    status: CryptoTransactionStatus
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def idempotency_key(self) -> str:
        """Dedupe key for at-least-once webhook delivery (partner_order_id, else transaction_id)."""
        key = self.partner_order_id or self.transaction_id
        if not key:
            raise CryptoLedgerError(
                "webhook event has no partner_order_id/transaction_id for idempotency",
                code="PAYBIS_WEBHOOK_NO_IDEMPOTENCY_KEY",
            )
        return key


def parse_event(payload: dict[str, Any]) -> PaybisWebhookEvent:
    """Structural parse of a PAYBIS webhook payload (known latin fields). Does NOT verify
    signature (see verify_signature). `status` derives from the payload's order/payment state."""
    if not isinstance(payload, dict):
        raise CryptoLedgerError("webhook payload must be a dict", code="PAYBIS_WEBHOOK_BAD_PAYLOAD")
    state = payload.get("status") or payload.get("state") or ""
    return PaybisWebhookEvent(
        event_type=str(payload.get("eventType") or payload.get("event_type") or ""),
        request_id=payload.get("requestId") or payload.get("request_id"),
        partner_order_id=payload.get("partnerOrderId") or payload.get("partner_order_id"),
        transaction_id=payload.get("transactionId") or payload.get("transaction_id"),
        status=map_order_status(state),
        raw=dict(payload),
    )


def verify_signature(payload: bytes, signature: str) -> bool:
    """FENCED: PAYBIS signed-request algorithm + signed fields are НЕИЗВЕСТНО until SRC-06.
    Raises rather than returning a guessed verdict (never silently accept/reject in Wave A)."""
    raise PaybisWebhookSpecUnknownError("signed-request algorithm / signed fields")
