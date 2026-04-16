"""
services/card_issuing/card_issuer.py
IL-CIM-01 | Phase 19

Card issuance: virtual and physical Mastercard/Visa cards.
PIN hashed with sha256 (never stored plain — I-12).
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import secrets

from services.card_issuing.models import (
    _SAMPLE_BINS,
    Card,
    CardAuditPort,
    CardNetwork,
    CardStatus,
    CardStorePort,
    CardType,
)


class CardIssuer:
    """Issues and manages card credentials. Invariant I-12: PIN never stored plain."""

    def __init__(self, store: CardStorePort, audit: CardAuditPort) -> None:
        self._store = store
        self._audit = audit

    async def issue_card(
        self,
        entity_id: str,
        card_type: CardType,
        network: CardNetwork,
        name_on_card: str,
        actor: str,
    ) -> Card:
        """Issue a new card in PENDING state. Assigns BIN range for the requested network."""
        bin_range = next((b for b in _SAMPLE_BINS if b.network == network), None)
        if bin_range is None:
            raise ValueError(f"No BIN range available for network {network}")

        last_four = "".join([str(secrets.randbelow(10)) for _ in range(4)])
        card_id = f"card-{secrets.token_hex(8)}"

        now = datetime.now(UTC)
        expiry_year = now.year + 3
        expiry_month = now.month

        card = Card(
            id=card_id,
            entity_id=entity_id,
            card_type=card_type,
            network=network,
            bin_range_id=bin_range.id,
            last_four=last_four,
            expiry_month=expiry_month,
            expiry_year=expiry_year,
            status=CardStatus.PENDING,
            created_at=now,
            activated_at=None,
            pin_hash=None,
            name_on_card=name_on_card,
        )

        await self._store.save(card)
        await self._audit.log(
            event_type="card.issued",
            card_id=card_id,
            entity_id=entity_id,
            actor=actor,
            details={"card_type": card_type.value, "network": network.value},
        )
        return card

    async def activate_card(self, card_id: str, actor: str) -> Card:
        """Activate a PENDING card. Raises ValueError if card is not PENDING."""
        card = await self._store.get(card_id)
        if card is None:
            raise ValueError(f"Card {card_id} not found")
        if card.status != CardStatus.PENDING:
            raise ValueError(f"Card {card_id} must be PENDING to activate; got {card.status}")

        now = datetime.now(UTC)
        updated = Card(
            id=card.id,
            entity_id=card.entity_id,
            card_type=card.card_type,
            network=card.network,
            bin_range_id=card.bin_range_id,
            last_four=card.last_four,
            expiry_month=card.expiry_month,
            expiry_year=card.expiry_year,
            status=CardStatus.ACTIVE,
            created_at=card.created_at,
            activated_at=now,
            pin_hash=card.pin_hash,
            name_on_card=card.name_on_card,
        )

        await self._store.save(updated)
        await self._audit.log(
            event_type="card.activated",
            card_id=card_id,
            entity_id=card.entity_id,
            actor=actor,
            details={"activated_at": now.isoformat()},
        )
        return updated

    async def set_pin(self, card_id: str, pin: str, actor: str) -> bool:
        """Set PIN (hashed). Raises ValueError if PIN is not exactly 4 digits."""
        if not (len(pin) == 4 and pin.isdigit()):
            raise ValueError("PIN must be exactly 4 digits")

        card = await self._store.get(card_id)
        if card is None:
            raise ValueError(f"Card {card_id} not found")

        pin_hash = hashlib.sha256(pin.encode()).hexdigest()

        updated = Card(
            id=card.id,
            entity_id=card.entity_id,
            card_type=card.card_type,
            network=card.network,
            bin_range_id=card.bin_range_id,
            last_four=card.last_four,
            expiry_month=card.expiry_month,
            expiry_year=card.expiry_year,
            status=card.status,
            created_at=card.created_at,
            activated_at=card.activated_at,
            pin_hash=pin_hash,
            name_on_card=card.name_on_card,
        )

        await self._store.save(updated)
        await self._audit.log(
            event_type="card.pin_set",
            card_id=card_id,
            entity_id=card.entity_id,
            actor=actor,
            details={"pin_updated": True},
        )
        return True

    async def get_card(self, card_id: str) -> Card | None:
        """Return card by ID or None if not found."""
        return await self._store.get(card_id)

    async def list_cards(self, entity_id: str) -> list[Card]:
        """Return all cards for an entity."""
        return await self._store.list_by_entity(entity_id)
