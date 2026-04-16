"""
tests/test_card_issuing/test_card_issuer.py
IL-CIM-01 | Phase 19 — CardIssuer unit tests.
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib

import pytest

from services.card_issuing.card_issuer import CardIssuer
from services.card_issuing.models import (
    CardNetwork,
    CardStatus,
    CardType,
    InMemoryCardAudit,
    InMemoryCardStore,
)


def _make_issuer() -> tuple[CardIssuer, InMemoryCardStore, InMemoryCardAudit]:
    store = InMemoryCardStore()
    audit = InMemoryCardAudit()
    issuer = CardIssuer(store, audit)
    return issuer, store, audit


# ── issue_card tests ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_issue_card_returns_pending_status() -> None:
    issuer, _, _ = _make_issuer()
    card = await issuer.issue_card(
        "ent-001", CardType.VIRTUAL, CardNetwork.MASTERCARD, "A User", "admin"
    )
    assert card.status == CardStatus.PENDING


@pytest.mark.asyncio
async def test_issue_card_last_four_is_4_digit_string() -> None:
    issuer, _, _ = _make_issuer()
    card = await issuer.issue_card(
        "ent-001", CardType.VIRTUAL, CardNetwork.MASTERCARD, "A User", "admin"
    )
    assert len(card.last_four) == 4
    assert card.last_four.isdigit()


@pytest.mark.asyncio
async def test_issue_card_creates_audit_entry() -> None:
    issuer, _, audit = _make_issuer()
    card = await issuer.issue_card(
        "ent-001", CardType.VIRTUAL, CardNetwork.MASTERCARD, "A User", "admin"
    )
    events = await audit.list_events(card.id)
    assert any(e["event_type"] == "card.issued" for e in events)


@pytest.mark.asyncio
async def test_issue_card_mastercard_assigns_mastercard_bin() -> None:
    issuer, _, _ = _make_issuer()
    card = await issuer.issue_card(
        "ent-001", CardType.VIRTUAL, CardNetwork.MASTERCARD, "A User", "admin"
    )
    assert card.bin_range_id == "bin-mc-001"


@pytest.mark.asyncio
async def test_issue_card_visa_assigns_visa_bin() -> None:
    issuer, _, _ = _make_issuer()
    card = await issuer.issue_card("ent-001", CardType.VIRTUAL, CardNetwork.VISA, "A User", "admin")
    assert card.bin_range_id == "bin-visa-001"


@pytest.mark.asyncio
async def test_issue_card_virtual_type() -> None:
    issuer, _, _ = _make_issuer()
    card = await issuer.issue_card(
        "ent-001", CardType.VIRTUAL, CardNetwork.MASTERCARD, "A User", "admin"
    )
    assert card.card_type == CardType.VIRTUAL


@pytest.mark.asyncio
async def test_issue_card_physical_type() -> None:
    issuer, _, _ = _make_issuer()
    card = await issuer.issue_card(
        "ent-001", CardType.PHYSICAL, CardNetwork.VISA, "A User", "admin"
    )
    assert card.card_type == CardType.PHYSICAL


@pytest.mark.asyncio
async def test_issue_card_expiry_year_is_current_plus_3() -> None:
    issuer, _, _ = _make_issuer()
    card = await issuer.issue_card(
        "ent-001", CardType.VIRTUAL, CardNetwork.MASTERCARD, "A User", "admin"
    )
    current_year = datetime.now(UTC).year
    assert card.expiry_year == current_year + 3


# ── activate_card tests ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_activate_card_returns_active_status() -> None:
    issuer, _, _ = _make_issuer()
    card = await issuer.issue_card(
        "ent-001", CardType.VIRTUAL, CardNetwork.MASTERCARD, "A User", "admin"
    )
    activated = await issuer.activate_card(card.id, "admin")
    assert activated.status == CardStatus.ACTIVE


@pytest.mark.asyncio
async def test_activate_card_sets_activated_at() -> None:
    issuer, _, _ = _make_issuer()
    card = await issuer.issue_card(
        "ent-001", CardType.VIRTUAL, CardNetwork.MASTERCARD, "A User", "admin"
    )
    activated = await issuer.activate_card(card.id, "admin")
    assert activated.activated_at is not None


@pytest.mark.asyncio
async def test_activate_card_creates_audit_entry() -> None:
    issuer, _, audit = _make_issuer()
    card = await issuer.issue_card(
        "ent-001", CardType.VIRTUAL, CardNetwork.MASTERCARD, "A User", "admin"
    )
    await issuer.activate_card(card.id, "admin")
    events = await audit.list_events(card.id)
    assert any(e["event_type"] == "card.activated" for e in events)


@pytest.mark.asyncio
async def test_activate_card_non_pending_raises_value_error() -> None:
    issuer, _, _ = _make_issuer()
    card = await issuer.issue_card(
        "ent-001", CardType.VIRTUAL, CardNetwork.MASTERCARD, "A User", "admin"
    )
    await issuer.activate_card(card.id, "admin")
    with pytest.raises(ValueError):
        await issuer.activate_card(card.id, "admin")


# ── set_pin tests ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_pin_returns_true() -> None:
    issuer, _, _ = _make_issuer()
    card = await issuer.issue_card(
        "ent-001", CardType.VIRTUAL, CardNetwork.MASTERCARD, "A User", "admin"
    )
    result = await issuer.set_pin(card.id, "1234", "admin")
    assert result is True


@pytest.mark.asyncio
async def test_set_pin_hash_is_not_plain_pin() -> None:
    issuer, store, _ = _make_issuer()
    card = await issuer.issue_card(
        "ent-001", CardType.VIRTUAL, CardNetwork.MASTERCARD, "A User", "admin"
    )
    await issuer.set_pin(card.id, "1234", "admin")
    updated = await store.get(card.id)
    assert updated is not None
    assert updated.pin_hash != "1234"


@pytest.mark.asyncio
async def test_set_pin_hash_is_sha256_hex() -> None:
    issuer, store, _ = _make_issuer()
    card = await issuer.issue_card(
        "ent-001", CardType.VIRTUAL, CardNetwork.MASTERCARD, "A User", "admin"
    )
    await issuer.set_pin(card.id, "1234", "admin")
    updated = await store.get(card.id)
    assert updated is not None
    expected = hashlib.sha256(b"1234").hexdigest()
    assert updated.pin_hash == expected


@pytest.mark.asyncio
async def test_set_pin_too_short_raises_value_error() -> None:
    issuer, _, _ = _make_issuer()
    card = await issuer.issue_card(
        "ent-001", CardType.VIRTUAL, CardNetwork.MASTERCARD, "A User", "admin"
    )
    with pytest.raises(ValueError):
        await issuer.set_pin(card.id, "123", "admin")


@pytest.mark.asyncio
async def test_set_pin_too_long_raises_value_error() -> None:
    issuer, _, _ = _make_issuer()
    card = await issuer.issue_card(
        "ent-001", CardType.VIRTUAL, CardNetwork.MASTERCARD, "A User", "admin"
    )
    with pytest.raises(ValueError):
        await issuer.set_pin(card.id, "12345", "admin")


@pytest.mark.asyncio
async def test_set_pin_creates_audit_entry_without_pin_value() -> None:
    issuer, _, audit = _make_issuer()
    card = await issuer.issue_card(
        "ent-001", CardType.VIRTUAL, CardNetwork.MASTERCARD, "A User", "admin"
    )
    await issuer.set_pin(card.id, "1234", "admin")
    events = await audit.list_events(card.id)
    pin_events = [e for e in events if e["event_type"] == "card.pin_set"]
    assert len(pin_events) == 1
    # PIN value must NOT appear in audit details
    assert "1234" not in str(pin_events[0]["details"])
    assert "pin" not in str(pin_events[0]["details"]).lower().replace("pin_updated", "")


# ── get_card / list_cards tests ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_card_returns_existing_card() -> None:
    issuer, _, _ = _make_issuer()
    card = await issuer.issue_card(
        "ent-001", CardType.VIRTUAL, CardNetwork.MASTERCARD, "A User", "admin"
    )
    result = await issuer.get_card(card.id)
    assert result is not None
    assert result.id == card.id


@pytest.mark.asyncio
async def test_get_card_returns_none_for_missing() -> None:
    issuer, _, _ = _make_issuer()
    result = await issuer.get_card("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_list_cards_returns_cards_for_entity() -> None:
    issuer, _, _ = _make_issuer()
    await issuer.issue_card("ent-001", CardType.VIRTUAL, CardNetwork.MASTERCARD, "A User", "admin")
    await issuer.issue_card("ent-001", CardType.PHYSICAL, CardNetwork.VISA, "A User", "admin")
    await issuer.issue_card("ent-002", CardType.VIRTUAL, CardNetwork.MASTERCARD, "B User", "admin")
    cards = await issuer.list_cards("ent-001")
    assert len(cards) == 2
    for c in cards:
        assert c.entity_id == "ent-001"
