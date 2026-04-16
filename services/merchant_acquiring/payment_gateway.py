"""
services/merchant_acquiring/payment_gateway.py
IL-MAG-01 | Phase 20

Card payment acceptance: authorisation, capture, void, refund, 3DS2.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
import uuid

from services.merchant_acquiring.models import (
    MAAuditPort,
    MerchantStatus,
    MerchantStorePort,
    PaymentAcceptance,
    PaymentResult,
    PaymentStorePort,
)

_REQUIRE_3DS_THRESHOLD = Decimal("30.00")  # PSD2 SCA threshold


class PaymentGateway:
    """Card payment acceptance gateway with 3DS2 support."""

    def __init__(
        self,
        merchant_store: MerchantStorePort,
        payment_store: PaymentStorePort,
        audit: MAAuditPort,
    ) -> None:
        self._merchant_store = merchant_store
        self._payment_store = payment_store
        self._audit = audit

    async def accept_payment(
        self,
        merchant_id: str,
        amount_str: str,
        currency: str,
        card_last_four: str,
        reference: str,
        actor: str,
    ) -> PaymentAcceptance:
        """Accept a card payment for a merchant."""
        merchant = await self._merchant_store.get(merchant_id)
        if merchant is None or merchant.status != MerchantStatus.ACTIVE:
            raise ValueError(f"Merchant {merchant_id!r} is not active or does not exist")

        amount = Decimal(amount_str)
        requires_3ds = amount >= _REQUIRE_3DS_THRESHOLD
        result = PaymentResult.PENDING_3DS if requires_3ds else PaymentResult.APPROVED

        now = datetime.now(UTC)
        payment = PaymentAcceptance(
            id=str(uuid.uuid4()),
            merchant_id=merchant_id,
            amount=amount,
            currency=currency,
            result=result,
            card_last_four=card_last_four,
            reference=reference,
            requires_3ds=requires_3ds,
            created_at=now,
            completed_at=now if not requires_3ds else None,
            acquirer_ref=f"ACQ-{uuid.uuid4().hex[:12].upper()}",
        )
        await self._payment_store.save(payment)
        await self._audit.log(
            "payment.accepted",
            merchant_id,
            actor,
            {
                "payment_id": payment.id,
                "amount": amount_str,
                "currency": currency,
                "result": result.value,
                "requires_3ds": requires_3ds,
            },
        )
        return payment

    async def complete_3ds(self, payment_id: str, actor: str) -> PaymentAcceptance:
        """Complete a 3DS2 challenge and approve the payment."""
        payment = await self._payment_store.get(payment_id)
        if payment is None:
            raise ValueError(f"Payment {payment_id!r} not found")
        if not payment.requires_3ds or payment.result != PaymentResult.PENDING_3DS:
            raise ValueError(f"Payment {payment_id!r} is not awaiting 3DS completion")

        updated = replace(
            payment,
            result=PaymentResult.APPROVED,
            completed_at=datetime.now(UTC),
        )
        await self._payment_store.save(updated)
        await self._audit.log(
            "payment.3ds_completed",
            payment.merchant_id,
            actor,
            {"payment_id": payment_id},
        )
        return updated

    async def void_payment(self, payment_id: str, actor: str) -> PaymentAcceptance:
        """Void an approved payment (reversal)."""
        payment = await self._payment_store.get(payment_id)
        if payment is None:
            raise ValueError(f"Payment {payment_id!r} not found")
        if payment.result != PaymentResult.APPROVED:
            raise ValueError(f"Payment {payment_id!r} is not in APPROVED state, cannot void")

        updated = replace(payment, result=PaymentResult.DECLINED)
        await self._payment_store.save(updated)
        await self._audit.log(
            "payment.voided",
            payment.merchant_id,
            actor,
            {"payment_id": payment_id},
        )
        return updated

    async def get_payment(self, payment_id: str) -> PaymentAcceptance | None:
        """Retrieve a payment by ID."""
        return await self._payment_store.get(payment_id)

    async def list_payments(self, merchant_id: str) -> list[PaymentAcceptance]:
        """List all payments for a merchant."""
        return await self._payment_store.list_by_merchant(merchant_id)
