"""
tests/test_card_issuing/test_card_lifecycle.py
IL-CIM-01 | Phase 19 — CardLifecycle unit tests.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from services.card_issuing.card_issuer import CardIssuer
from services.card_issuing.card_lifecycle import CardLifecycle
from services.card_issuing.models import (
    Card,
    CardNetwork,
    CardStatus,
    CardType,
    InMemoryCardAudit,
    InMemoryCardStore,
)


def _make_services() -> tuple[CardIssuer, CardLifecycle, InMemoryCardStore, InMemoryCardAudit]:
    store = InMemoryCardStore()
    audit = InMemoryCardAudit()
    issuer = CardIssuer(store, audit)
    lifecycle = CardLifecycle(store, audit)
    return issuer, lifecycle, store, audit


async def _issue_active_card(
    issuer: CardIssuer,
    entity_id: str = "ent-001",
) -> Card:
    card = await issuer.issue_card(
        entity_id, CardType.VIRTUAL, CardNetwork.MASTERCARD, "A User", "admin"
    )
    return await issuer.activate_card(card.id, "admin")


# ── freeze tests ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_freeze_active_card_becomes_frozen() -> None:
    issuer, lifecycle, _, _ = _make_services()
    card = await _issue_active_card(issuer)
    frozen = await lifecycle.freeze(card.id, "admin")
    assert frozen.status == CardStatus.FROZEN


@pytest.mark.asyncio
async def test_freeze_creates_audit_entry() -> None:
    issuer, lifecycle, _, audit = _make_services()
    card = await _issue_active_card(issuer)
    await lifecycle.freeze(card.id, "admin", reason="suspected fraud")
    events = await audit.list_events(card.id)
    assert any(e["event_type"] == "card.frozen" for e in events)


@pytest.mark.asyncio
async def test_freeze_non_active_card_raises_value_error() -> None:
    issuer, lifecycle, _, _ = _make_services()
    card = await issuer.issue_card(
        "ent-001", CardType.VIRTUAL, CardNetwork.MASTERCARD, "A User", "admin"
    )
    # Card is PENDING, not ACTIVE
    with pytest.raises(ValueError):
        await lifecycle.freeze(card.id, "admin")


# ── unfreeze tests ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unfreeze_frozen_card_becomes_active() -> None:
    issuer, lifecycle, _, _ = _make_services()
    card = await _issue_active_card(issuer)
    await lifecycle.freeze(card.id, "admin")
    unfrozen = await lifecycle.unfreeze(card.id, "admin")
    assert unfrozen.status == CardStatus.ACTIVE


@pytest.mark.asyncio
async def test_unfreeze_creates_audit_entry() -> None:
    issuer, lifecycle, _, audit = _make_services()
    card = await _issue_active_card(issuer)
    await lifecycle.freeze(card.id, "admin")
    await lifecycle.unfreeze(card.id, "admin")
    events = await audit.list_events(card.id)
    assert any(e["event_type"] == "card.unfrozen" for e in events)


@pytest.mark.asyncio
async def test_unfreeze_non_frozen_raises_value_error() -> None:
    issuer, lifecycle, _, _ = _make_services()
    card = await _issue_active_card(issuer)
    with pytest.raises(ValueError):
        await lifecycle.unfreeze(card.id, "admin")


# ── block tests ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_block_active_card_becomes_blocked() -> None:
    issuer, lifecycle, _, _ = _make_services()
    card = await _issue_active_card(issuer)
    blocked = await lifecycle.block(card.id, "admin", "fraud confirmed")
    assert blocked.status == CardStatus.BLOCKED


@pytest.mark.asyncio
async def test_block_frozen_card_becomes_blocked() -> None:
    issuer, lifecycle, _, _ = _make_services()
    card = await _issue_active_card(issuer)
    await lifecycle.freeze(card.id, "admin")
    blocked = await lifecycle.block(card.id, "admin", "escalated")
    assert blocked.status == CardStatus.BLOCKED


@pytest.mark.asyncio
async def test_block_creates_audit_entry() -> None:
    issuer, lifecycle, _, audit = _make_services()
    card = await _issue_active_card(issuer)
    await lifecycle.block(card.id, "admin", "fraud")
    events = await audit.list_events(card.id)
    assert any(e["event_type"] == "card.blocked" for e in events)


@pytest.mark.asyncio
async def test_block_already_blocked_raises_value_error() -> None:
    issuer, lifecycle, _, _ = _make_services()
    card = await _issue_active_card(issuer)
    await lifecycle.block(card.id, "admin", "fraud")
    with pytest.raises(ValueError):
        await lifecycle.block(card.id, "admin", "again")


# ── replace tests ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_replace_returns_new_pending_card() -> None:
    issuer, lifecycle, _, _ = _make_services()
    card = await _issue_active_card(issuer)
    new_card = await lifecycle.replace(card.id, "admin", "lost card")
    assert new_card.status == CardStatus.PENDING
    assert new_card.id != card.id


@pytest.mark.asyncio
async def test_replace_old_card_becomes_blocked() -> None:
    issuer, lifecycle, store, _ = _make_services()
    card = await _issue_active_card(issuer)
    await lifecycle.replace(card.id, "admin", "stolen")
    old_card = await store.get(card.id)
    assert old_card is not None
    assert old_card.status == CardStatus.BLOCKED


@pytest.mark.asyncio
async def test_replace_creates_audit_entry() -> None:
    issuer, lifecycle, _, audit = _make_services()
    card = await _issue_active_card(issuer)
    new_card = await lifecycle.replace(card.id, "admin", "lost")
    events = await audit.list_events(new_card.id)
    assert any(e["event_type"] == "card.replaced" for e in events)


# ── check_expiry tests ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_expiry_future_card_returns_false() -> None:
    issuer, lifecycle, _, _ = _make_services()
    card = await _issue_active_card(issuer)
    result = await lifecycle.check_expiry(card.id)
    assert result is False


@pytest.mark.asyncio
async def test_check_expiry_past_card_returns_true() -> None:
    store = InMemoryCardStore()
    audit = InMemoryCardAudit()
    lifecycle = CardLifecycle(store, audit)
    now = datetime.now(UTC)
    expired_card = Card(
        id="card-expired",
        entity_id="ent-001",
        card_type=CardType.VIRTUAL,
        network=CardNetwork.MASTERCARD,
        bin_range_id="bin-mc-001",
        last_four="9999",
        expiry_month=1,
        expiry_year=2020,
        status=CardStatus.ACTIVE,
        created_at=now,
        activated_at=now,
        pin_hash=None,
        name_on_card="Old User",
    )
    await store.save(expired_card)
    result = await lifecycle.check_expiry("card-expired")
    assert result is True


# ── expire_card tests ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_expire_card_sets_expired_status() -> None:
    issuer, lifecycle, _, _ = _make_services()
    card = await _issue_active_card(issuer)
    expired = await lifecycle.expire_card(card.id, "system")
    assert expired.status == CardStatus.EXPIRED


@pytest.mark.asyncio
async def test_expire_card_creates_audit_entry() -> None:
    issuer, lifecycle, _, audit = _make_services()
    card = await _issue_active_card(issuer)
    await lifecycle.expire_card(card.id, "system")
    events = await audit.list_events(card.id)
    assert any(e["event_type"] == "card.expired" for e in events)


# ── full lifecycle tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_full_lifecycle_issue_activate_freeze_unfreeze_block() -> None:
    issuer, lifecycle, store, _ = _make_services()

    card = await issuer.issue_card(
        "ent-001", CardType.VIRTUAL, CardNetwork.MASTERCARD, "A User", "admin"
    )
    assert card.status == CardStatus.PENDING

    card = await issuer.activate_card(card.id, "admin")
    assert card.status == CardStatus.ACTIVE

    card = await lifecycle.freeze(card.id, "admin", "check")
    assert card.status == CardStatus.FROZEN

    card = await lifecycle.unfreeze(card.id, "admin")
    assert card.status == CardStatus.ACTIVE

    card = await lifecycle.block(card.id, "admin", "fraud confirmed")
    assert card.status == CardStatus.BLOCKED


@pytest.mark.asyncio
async def test_replace_frozen_card() -> None:
    issuer, lifecycle, store, _ = _make_services()
    card = await _issue_active_card(issuer)
    await lifecycle.freeze(card.id, "admin", "check")
    new_card = await lifecycle.replace(card.id, "admin", "stolen while frozen")
    assert new_card.status == CardStatus.PENDING
    old = await store.get(card.id)
    assert old is not None
    assert old.status == CardStatus.BLOCKED
