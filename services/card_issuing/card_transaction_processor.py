"""
services/card_issuing/card_transaction_processor.py
IL-CIM-01 | Phase 19

Card transaction processing: authorisation, clearing, settlement stubs.
All amounts use Decimal (I-01).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import secrets

from services.card_issuing.models import (
    AuthorisationResult,
    CardAuditPort,
    CardAuthorisation,
    CardStatus,
    CardStorePort,
    CardTransaction,
    TransactionStorePort,
    TransactionType,
)
from services.card_issuing.spend_control import SpendControl


class CardTransactionProcessor:
    """Processes card authorisations, clearing, and settlement."""

    def __init__(
        self,
        card_store: CardStorePort,
        txn_store: TransactionStorePort,
        spend_control: SpendControl,
        audit: CardAuditPort,
    ) -> None:
        self._card_store = card_store
        self._txn_store = txn_store
        self._spend_control = spend_control
        self._audit = audit

    async def authorise(
        self,
        card_id: str,
        amount_str: str,
        currency: str,
        merchant_name: str,
        merchant_mcc: str,
        merchant_country: str,
        transaction_type: TransactionType = TransactionType.PURCHASE,
        actor: str = "system",
    ) -> CardAuthorisation:
        """
        Authorise a card transaction.
        Declines if card is not ACTIVE or spend limits are exceeded.
        """
        card = await self._card_store.get(card_id)
        amount = Decimal(amount_str)
        auth_id = f"auth-{secrets.token_hex(8)}"
        now = datetime.now(UTC)

        if card is None or card.status != CardStatus.ACTIVE:
            decline_reason = "Card not active"
            auth = CardAuthorisation(
                id=auth_id,
                card_id=card_id,
                amount=amount,
                currency=currency,
                merchant_name=merchant_name,
                merchant_mcc=merchant_mcc,
                merchant_country=merchant_country,
                result=AuthorisationResult.DECLINED,
                decline_reason=decline_reason,
                authorised_at=now,
                transaction_type=transaction_type,
            )
            await self._txn_store.save_auth(auth)
            await self._audit.log(
                event_type="card.declined",
                card_id=card_id,
                entity_id=card.entity_id if card else "",
                actor=actor,
                details={"reason": decline_reason},
            )
            return auth

        allowed, reason = await self._spend_control.check_authorisation(
            card_id, amount, currency, merchant_mcc, merchant_country
        )

        if not allowed:
            auth = CardAuthorisation(
                id=auth_id,
                card_id=card_id,
                amount=amount,
                currency=currency,
                merchant_name=merchant_name,
                merchant_mcc=merchant_mcc,
                merchant_country=merchant_country,
                result=AuthorisationResult.DECLINED,
                decline_reason=reason,
                authorised_at=now,
                transaction_type=transaction_type,
            )
            await self._txn_store.save_auth(auth)
            await self._audit.log(
                event_type="card.declined",
                card_id=card_id,
                entity_id=card.entity_id,
                actor=actor,
                details={"reason": reason},
            )
            return auth

        auth = CardAuthorisation(
            id=auth_id,
            card_id=card_id,
            amount=amount,
            currency=currency,
            merchant_name=merchant_name,
            merchant_mcc=merchant_mcc,
            merchant_country=merchant_country,
            result=AuthorisationResult.APPROVED,
            decline_reason=None,
            authorised_at=now,
            transaction_type=transaction_type,
        )
        await self._txn_store.save_auth(auth)
        await self._audit.log(
            event_type="card.authorised",
            card_id=card_id,
            entity_id=card.entity_id,
            actor=actor,
            details={"amount": str(amount), "currency": currency},
        )
        return auth

    async def clear_transaction(self, auth_id: str, actor: str = "system") -> CardTransaction:
        """Clear an authorisation into a posted transaction."""
        auth = await self._txn_store.get_auth(auth_id)
        if auth is None:
            raise ValueError(f"Authorisation {auth_id} not found")

        card = await self._card_store.get(auth.card_id)
        entity_id = card.entity_id if card else ""

        txn_id = f"txn-{secrets.token_hex(8)}"
        txn = CardTransaction(
            id=txn_id,
            card_id=auth.card_id,
            authorisation_id=auth_id,
            amount=auth.amount,
            currency=auth.currency,
            merchant_name=auth.merchant_name,
            merchant_mcc=auth.merchant_mcc,
            posted_at=datetime.now(UTC),
            transaction_type=auth.transaction_type,
            settled=False,
        )
        await self._txn_store.save_txn(txn)
        await self._audit.log(
            event_type="card.cleared",
            card_id=auth.card_id,
            entity_id=entity_id,
            actor=actor,
            details={"auth_id": auth_id, "txn_id": txn_id},
        )
        return txn

    async def list_transactions(self, card_id: str) -> list[CardTransaction]:
        """List all cleared transactions for a card."""
        return await self._txn_store.list_txns(card_id)

    async def list_authorisations(self, card_id: str) -> list[CardAuthorisation]:
        """List all authorisations for a card."""
        return await self._txn_store.list_auths(card_id)
