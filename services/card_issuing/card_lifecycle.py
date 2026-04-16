"""
services/card_issuing/card_lifecycle.py
IL-CIM-01 | Phase 19

Card lifecycle: freeze, unfreeze, block, replace, expiry.
Block and replace require HITL (L4 gate — I-27).
"""

from __future__ import annotations

from datetime import UTC, datetime
import secrets

from services.card_issuing.models import (
    Card,
    CardAuditPort,
    CardStatus,
    CardStorePort,
)


class CardLifecycle:
    """Manages card state transitions. Block/replace are irreversible HITL operations."""

    def __init__(self, store: CardStorePort, audit: CardAuditPort) -> None:
        self._store = store
        self._audit = audit

    def _replace_card(self, card: Card, **overrides: object) -> Card:
        """Create a new frozen Card with specified field overrides."""
        fields = {
            "id": card.id,
            "entity_id": card.entity_id,
            "card_type": card.card_type,
            "network": card.network,
            "bin_range_id": card.bin_range_id,
            "last_four": card.last_four,
            "expiry_month": card.expiry_month,
            "expiry_year": card.expiry_year,
            "status": card.status,
            "created_at": card.created_at,
            "activated_at": card.activated_at,
            "pin_hash": card.pin_hash,
            "name_on_card": card.name_on_card,
        }
        fields.update(overrides)
        return Card(**fields)  # type: ignore[arg-type]

    async def freeze(self, card_id: str, actor: str, reason: str = "") -> Card:
        """Freeze an ACTIVE card. Raises ValueError if not ACTIVE."""
        card = await self._store.get(card_id)
        if card is None:
            raise ValueError(f"Card {card_id} not found")
        if card.status != CardStatus.ACTIVE:
            raise ValueError(f"Card {card_id} must be ACTIVE to freeze; got {card.status}")

        updated = self._replace_card(card, status=CardStatus.FROZEN)
        await self._store.save(updated)
        await self._audit.log(
            event_type="card.frozen",
            card_id=card_id,
            entity_id=card.entity_id,
            actor=actor,
            details={"reason": reason},
        )
        return updated

    async def unfreeze(self, card_id: str, actor: str) -> Card:
        """Unfreeze a FROZEN card. Raises ValueError if not FROZEN."""
        card = await self._store.get(card_id)
        if card is None:
            raise ValueError(f"Card {card_id} not found")
        if card.status != CardStatus.FROZEN:
            raise ValueError(f"Card {card_id} must be FROZEN to unfreeze; got {card.status}")

        updated = self._replace_card(card, status=CardStatus.ACTIVE)
        await self._store.save(updated)
        await self._audit.log(
            event_type="card.unfrozen",
            card_id=card_id,
            entity_id=card.entity_id,
            actor=actor,
            details={},
        )
        return updated

    async def block(self, card_id: str, actor: str, reason: str) -> Card:
        """Block a card (HITL operation). Raises ValueError if already BLOCKED."""
        card = await self._store.get(card_id)
        if card is None:
            raise ValueError(f"Card {card_id} not found")
        if card.status == CardStatus.BLOCKED:
            raise ValueError(f"Card {card_id} is already BLOCKED")

        updated = self._replace_card(card, status=CardStatus.BLOCKED)
        await self._store.save(updated)
        await self._audit.log(
            event_type="card.blocked",
            card_id=card_id,
            entity_id=card.entity_id,
            actor=actor,
            details={"reason": reason, "hitl": True},
        )
        return updated

    async def replace(self, card_id: str, actor: str, reason: str) -> Card:
        """Block old card and issue a replacement card in PENDING state (HITL)."""
        old_card = await self._store.get(card_id)
        if old_card is None:
            raise ValueError(f"Card {card_id} not found")

        await self.block(card_id, actor, reason=f"replaced: {reason}")

        now = datetime.now(UTC)
        new_id = f"card-{secrets.token_hex(8)}"
        new_card = Card(
            id=new_id,
            entity_id=old_card.entity_id,
            card_type=old_card.card_type,
            network=old_card.network,
            bin_range_id=old_card.bin_range_id,
            last_four=old_card.last_four,
            expiry_month=old_card.expiry_month,
            expiry_year=old_card.expiry_year + 3,
            status=CardStatus.PENDING,
            created_at=now,
            activated_at=None,
            pin_hash=None,
            name_on_card=old_card.name_on_card,
        )

        await self._store.save(new_card)
        await self._audit.log(
            event_type="card.replaced",
            card_id=new_id,
            entity_id=old_card.entity_id,
            actor=actor,
            details={"old_card_id": card_id, "reason": reason, "hitl": True},
        )
        return new_card

    async def check_expiry(self, card_id: str) -> bool:
        """Return True if card has expired (expiry year/month < today)."""
        card = await self._store.get(card_id)
        if card is None:
            raise ValueError(f"Card {card_id} not found")

        today = datetime.now(UTC)
        if card.expiry_year < today.year:
            return True
        if card.expiry_year == today.year and card.expiry_month < today.month:
            return True
        return False

    async def expire_card(self, card_id: str, actor: str) -> Card:
        """Mark a card as EXPIRED."""
        card = await self._store.get(card_id)
        if card is None:
            raise ValueError(f"Card {card_id} not found")

        updated = self._replace_card(card, status=CardStatus.EXPIRED)
        await self._store.save(updated)
        await self._audit.log(
            event_type="card.expired",
            card_id=card_id,
            entity_id=card.entity_id,
            actor=actor,
            details={},
        )
        return updated
