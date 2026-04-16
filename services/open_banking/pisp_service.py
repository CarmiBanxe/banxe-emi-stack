"""
services/open_banking/pisp_service.py
IL-OBK-01 | Phase 15

Payment Initiation Service Provider (PSR 2017 / PSD2 Art.66)
Single, bulk, and standing order payments.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
import uuid

from services.open_banking.consent_manager import ConsentManager
from services.open_banking.models import (
    ConsentStatus,
    ConsentType,
    OBAuditTrailPort,
    PaymentGatewayPort,
    PaymentInitiation,
    PaymentStatus,
    _new_event,
)


class PISPService:
    """Payment Initiation Service Provider — PSD2 Art.66."""

    def __init__(
        self,
        consent_manager: ConsentManager,
        gateway: PaymentGatewayPort,
        audit: OBAuditTrailPort,
    ) -> None:
        self._consent_manager = consent_manager
        self._gateway = gateway
        self._audit = audit

    async def initiate_payment(
        self,
        consent_id: str,
        entity_id: str,
        aspsp_id: str,
        amount: Decimal,
        currency: str,
        creditor_iban: str,
        creditor_name: str,
        actor: str,
        debtor_iban: str | None = None,
        reference: str = "",
    ) -> PaymentInitiation:
        """Initiate a single payment via the ASPSP.

        Raises ValueError if the consent is not valid for PISP.
        """
        consent = await self._consent_manager.get_consent(consent_id)
        if consent is None:
            raise ValueError(f"Consent not found: {consent_id}")

        if consent.type != ConsentType.PISP:
            raise ValueError(
                f"Consent {consent_id} is not a PISP consent (type={consent.type.value})"
            )

        if consent.status != ConsentStatus.AUTHORISED:
            raise ValueError(
                f"Consent {consent_id} is not authorised (status={consent.status.value})"
            )

        now = datetime.now(UTC)
        payment = PaymentInitiation(
            id=str(uuid.uuid4()),
            consent_id=consent_id,
            entity_id=entity_id,
            aspsp_id=aspsp_id,
            amount=amount,
            currency=currency,
            creditor_iban=creditor_iban,
            creditor_name=creditor_name,
            debtor_iban=debtor_iban,
            reference=reference,
            status=PaymentStatus.PENDING,
            created_at=now,
            end_to_end_id=str(uuid.uuid4()),
        )

        try:
            aspsp_payment_id = await self._gateway.submit_payment(payment)
        except ValueError:
            await self._audit.append(
                _new_event(
                    event_type="payment.initiated",
                    entity_id=entity_id,
                    actor=actor,
                    consent_id=consent_id,
                    payment_id=payment.id,
                    details={"status": PaymentStatus.FAILED.value, "error": "gateway_rejected"},
                )
            )
            raise

        accepted = replace(
            payment,
            status=PaymentStatus.ACCEPTED,
            aspsp_payment_id=aspsp_payment_id,
        )
        await self._audit.append(
            _new_event(
                event_type="payment.initiated",
                entity_id=entity_id,
                actor=actor,
                consent_id=consent_id,
                payment_id=accepted.id,
                details={
                    "aspsp_payment_id": aspsp_payment_id,
                    "amount": str(amount),
                    "currency": currency,
                    "status": PaymentStatus.ACCEPTED.value,
                },
            )
        )
        return accepted

    async def get_payment_status(self, payment: PaymentInitiation) -> PaymentStatus:
        """Retrieve the current payment status from the ASPSP gateway."""
        if payment.aspsp_payment_id is None:
            return payment.status
        return await self._gateway.get_payment_status(
            payment.aspsp_payment_id,
            payment.aspsp_id,
        )

    async def create_bulk_payment(
        self,
        consent_id: str,
        entity_id: str,
        aspsp_id: str,
        payments: list[dict],
        actor: str,
    ) -> list[PaymentInitiation]:
        """Initiate multiple payments for the same consent."""
        results: list[PaymentInitiation] = []
        for p in payments:
            initiated = await self.initiate_payment(
                consent_id=consent_id,
                entity_id=entity_id,
                aspsp_id=aspsp_id,
                amount=Decimal(str(p["amount"])),
                currency=p["currency"],
                creditor_iban=p["creditor_iban"],
                creditor_name=p["creditor_name"],
                debtor_iban=p.get("debtor_iban"),
                reference=p.get("reference", ""),
                actor=actor,
            )
            results.append(initiated)
        return results
