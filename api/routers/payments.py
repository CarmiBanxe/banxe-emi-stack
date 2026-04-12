"""
api/routers/payments.py — Payment initiation and status endpoints
IL-046 | banxe-emi-stack

POST /v1/payments          — initiate payment (FPS / SEPA CT / SEPA Instant)
GET  /v1/payments          — list all payments (sandbox only)
GET  /v1/payments/{id}     — get payment status by idempotency key

FCA compliance:
  - Idempotency enforced (same key → same result, no double spend)
  - Amounts as Decimal strings (I-05, never float)
  - All payment events logged to ClickHouse in production (I-24)
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import uuid

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_payment_service
from api.models.payments import InitiatePaymentRequest, PaymentResponse
from services.payment.mock_payment_adapter import MockPaymentAdapter
from services.payment.payment_port import (
    BankAccount,
    PaymentDirection,
    PaymentIntent,
)

router = APIRouter(tags=["Payments"])


def _result_to_response(result) -> PaymentResponse:  # type: ignore[return]
    return PaymentResponse(
        payment_id=result.idempotency_key,
        provider_payment_id=result.provider_payment_id,
        rail=result.rail,
        status=result.status,
        amount=str(result.amount),
        currency=result.currency,
        direction=PaymentDirection.OUTBOUND,
        reference="",
        failure_reason=result.error_message,
        created_at=result.submitted_at,
    )


@router.post(
    "/payments",
    response_model=PaymentResponse,
    status_code=201,
    summary="Initiate a payment",
)
def initiate_payment(
    body: InitiatePaymentRequest,
    svc: MockPaymentAdapter = Depends(get_payment_service),
) -> PaymentResponse:
    """
    Submit a payment instruction.

    - FPS: UK domestic GBP, near-instant (< 2 hours)
    - SEPA_CT: EUR cross-border, D+1
    - SEPA_INSTANT: EUR instant (< 10 seconds, 24/7)

    Idempotency: re-sending the same idempotency_key returns the original result.
    Amounts must be decimal strings (e.g. "100.00") — never float.
    """
    debtor = BankAccount(
        iban=body.debtor_account.iban,
        sort_code=body.debtor_account.sort_code,
        account_number=body.debtor_account.account_number,
        bic=body.debtor_account.bic,
        account_holder_name=body.debtor_account.holder_name,
    )
    creditor = BankAccount(
        iban=body.creditor_account.iban,
        sort_code=body.creditor_account.sort_code,
        account_number=body.creditor_account.account_number,
        bic=body.creditor_account.bic,
        account_holder_name=body.creditor_account.holder_name,
    )

    try:
        intent = PaymentIntent(
            idempotency_key=body.idempotency_key,
            rail=body.rail,
            direction=PaymentDirection.OUTBOUND,
            amount=Decimal(body.amount),
            currency=body.currency.upper(),
            debtor_account=debtor,
            creditor_account=creditor,
            reference=body.reference,
            end_to_end_id=str(uuid.uuid4()),
            requested_at=datetime.now(UTC),
            metadata={"customer_id": body.customer_id},
        )
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    result = svc.submit_payment(intent)
    return _result_to_response(result)


@router.get(
    "/payments",
    response_model=list[PaymentResponse],
    summary="List all payments (sandbox)",
)
def list_payments(
    svc: MockPaymentAdapter = Depends(get_payment_service),
) -> list[PaymentResponse]:
    """Returns all payments in the in-memory sandbox. Not available in production."""
    return [_result_to_response(r) for r in svc.get_all_payments()]


@router.get(
    "/payments/{idempotency_key}",
    response_model=PaymentResponse,
    summary="Get payment status",
)
def get_payment(
    idempotency_key: str,
    svc: MockPaymentAdapter = Depends(get_payment_service),
) -> PaymentResponse:
    result = svc.get_payment_status(idempotency_key)
    if result.status.value == "NOT_FOUND":
        raise HTTPException(status_code=404, detail=f"Payment {idempotency_key} not found")
    return _result_to_response(result)
