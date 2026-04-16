"""
services/card_issuing/card_agent.py
IL-CIM-01 | Phase 19

Card Agent — orchestrates card lifecycle.
L2: issue, activate, set PIN, set limits, authorise, list transactions.
L4: block, replace (irreversible — I-27 HITL gate).
"""

from __future__ import annotations

from decimal import Decimal

from services.card_issuing.card_issuer import CardIssuer
from services.card_issuing.card_lifecycle import CardLifecycle
from services.card_issuing.card_transaction_processor import CardTransactionProcessor
from services.card_issuing.fraud_shield import FraudShield
from services.card_issuing.models import (
    CardAuditPort,
    CardNetwork,
    CardType,
    SpendPeriod,
)
from services.card_issuing.spend_control import SpendControl


class CardAgent:
    """High-level orchestrator for card issuing, lifecycle, and transaction ops."""

    def __init__(
        self,
        issuer: CardIssuer,
        lifecycle: CardLifecycle,
        spend_control: SpendControl,
        processor: CardTransactionProcessor,
        fraud_shield: FraudShield,
        audit: CardAuditPort,
    ) -> None:
        self._issuer = issuer
        self._lifecycle = lifecycle
        self._spend_control = spend_control
        self._processor = processor
        self._fraud_shield = fraud_shield
        self._audit = audit

    async def issue_card(
        self,
        entity_id: str,
        card_type_str: str,
        network_str: str,
        name_on_card: str,
        actor: str,
    ) -> dict:
        card_type = CardType(card_type_str)
        network = CardNetwork(network_str)
        card = await self._issuer.issue_card(entity_id, card_type, network, name_on_card, actor)
        return self._card_to_dict(card)

    async def activate_card(self, card_id: str, actor: str) -> dict:
        card = await self._issuer.activate_card(card_id, actor)
        return self._card_to_dict(card)

    async def set_pin(self, card_id: str, pin: str, actor: str) -> dict:
        result = await self._issuer.set_pin(card_id, pin, actor)
        return {"success": result, "card_id": card_id}

    async def freeze_card(self, card_id: str, actor: str, reason: str = "") -> dict:
        card = await self._lifecycle.freeze(card_id, actor, reason)
        return self._card_to_dict(card)

    async def unfreeze_card(self, card_id: str, actor: str) -> dict:
        card = await self._lifecycle.unfreeze(card_id, actor)
        return self._card_to_dict(card)

    async def block_card(self, card_id: str, actor: str, reason: str) -> dict:
        card = await self._lifecycle.block(card_id, actor, reason)
        return self._card_to_dict(card)

    async def set_limits(
        self,
        card_id: str,
        period_str: str,
        amount_str: str,
        currency: str,
        blocked_mccs: list[str],
        actor: str,
    ) -> dict:
        period = SpendPeriod(period_str)
        limit = await self._spend_control.set_limits(
            card_id=card_id,
            period=period,
            limit_amount_str=amount_str,
            currency=currency,
            blocked_mccs=blocked_mccs,
            actor=actor,
        )
        return {
            "card_id": limit.card_id,
            "period": limit.period.value,
            "limit_amount": str(limit.limit_amount),
            "currency": limit.currency,
            "blocked_mccs": limit.blocked_mccs,
            "geo_restrictions": limit.geo_restrictions,
        }

    async def authorise_transaction(
        self,
        card_id: str,
        amount_str: str,
        currency: str,
        merchant_name: str,
        mcc: str,
        country: str,
        actor: str,
    ) -> dict:
        auth = await self._processor.authorise(
            card_id=card_id,
            amount_str=amount_str,
            currency=currency,
            merchant_name=merchant_name,
            merchant_mcc=mcc,
            merchant_country=country,
            actor=actor,
        )
        return {
            "id": auth.id,
            "card_id": auth.card_id,
            "amount": str(auth.amount),
            "currency": auth.currency,
            "merchant_name": auth.merchant_name,
            "result": auth.result.value,
            "decline_reason": auth.decline_reason,
            "authorised_at": auth.authorised_at.isoformat(),
        }

    async def get_card(self, card_id: str) -> dict | None:
        card = await self._issuer.get_card(card_id)
        if card is None:
            return None
        return self._card_to_dict(card)

    async def list_cards(self, entity_id: str) -> list[dict]:
        cards = await self._issuer.list_cards(entity_id)
        return [self._card_to_dict(c) for c in cards]

    async def list_transactions(self, card_id: str) -> list[dict]:
        txns = await self._processor.list_transactions(card_id)
        return [
            {
                "id": t.id,
                "card_id": t.card_id,
                "authorisation_id": t.authorisation_id,
                "amount": str(t.amount),
                "currency": t.currency,
                "merchant_name": t.merchant_name,
                "merchant_mcc": t.merchant_mcc,
                "posted_at": t.posted_at.isoformat(),
                "transaction_type": t.transaction_type.value,
                "settled": t.settled,
            }
            for t in txns
        ]

    async def get_fraud_assessment(
        self,
        card_id: str,
        amount_str: str,
        mcc: str,
        country: str,
    ) -> dict:
        amount = Decimal(amount_str)
        assessment = await self._fraud_shield.assess(card_id, amount, mcc, country)
        return {
            "card_id": assessment.card_id,
            "risk_score": assessment.risk_score,
            "is_suspicious": assessment.is_suspicious,
            "triggered_rules": assessment.triggered_rules,
            "assessed_at": assessment.assessed_at.isoformat(),
        }

    async def get_audit_log(self, card_id: str | None = None) -> list[dict]:
        return await self._audit.list_events(card_id)

    @staticmethod
    def _card_to_dict(card) -> dict:  # type: ignore[no-untyped-def]
        return {
            "id": card.id,
            "entity_id": card.entity_id,
            "card_type": card.card_type.value,
            "network": card.network.value,
            "bin_range_id": card.bin_range_id,
            "last_four": card.last_four,
            "expiry_month": card.expiry_month,
            "expiry_year": card.expiry_year,
            "status": card.status.value,
            "created_at": card.created_at.isoformat(),
            "activated_at": card.activated_at.isoformat() if card.activated_at else None,
            "name_on_card": card.name_on_card,
        }
