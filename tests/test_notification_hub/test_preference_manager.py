"""
tests/test_notification_hub/test_preference_manager.py
IL-NHB-01 | Phase 18 — PreferenceManager tests
"""

from __future__ import annotations

import pytest

from services.notification_hub.models import (
    Channel,
    InMemoryPreferenceStore,
    NotificationCategory,
)
from services.notification_hub.preference_manager import PreferenceManager

# ─── Fixtures ─────────────────────────────────────────────────────────────────


def _make_manager() -> PreferenceManager:
    return PreferenceManager(store=InMemoryPreferenceStore())


# ─── Default opt-in / opt-out tests ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_security_default_opt_in_no_stored_pref() -> None:
    manager = _make_manager()
    result = await manager.is_opted_in("entity-001", Channel.EMAIL, NotificationCategory.SECURITY)
    assert result is True


@pytest.mark.asyncio
async def test_operational_default_opt_in_no_stored_pref() -> None:
    manager = _make_manager()
    result = await manager.is_opted_in("entity-001", Channel.SMS, NotificationCategory.OPERATIONAL)
    assert result is True


@pytest.mark.asyncio
async def test_payment_default_opt_out_no_stored_pref() -> None:
    manager = _make_manager()
    result = await manager.is_opted_in("entity-001", Channel.EMAIL, NotificationCategory.PAYMENT)
    assert result is False


@pytest.mark.asyncio
async def test_marketing_default_opt_out_no_stored_pref() -> None:
    manager = _make_manager()
    result = await manager.is_opted_in("entity-001", Channel.EMAIL, NotificationCategory.MARKETING)
    assert result is False


@pytest.mark.asyncio
async def test_stored_opt_in_overrides_default() -> None:
    manager = _make_manager()
    await manager.set_preference("entity-001", Channel.EMAIL, NotificationCategory.PAYMENT, True)
    result = await manager.is_opted_in("entity-001", Channel.EMAIL, NotificationCategory.PAYMENT)
    assert result is True


@pytest.mark.asyncio
async def test_stored_opt_out_for_security_overrides_default() -> None:
    manager = _make_manager()
    await manager.set_preference("entity-001", Channel.EMAIL, NotificationCategory.SECURITY, False)
    result = await manager.is_opted_in("entity-001", Channel.EMAIL, NotificationCategory.SECURITY)
    assert result is False


# ─── set_preference() tests ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_preference_saves_to_store() -> None:
    store = InMemoryPreferenceStore()
    manager = PreferenceManager(store=store)
    await manager.set_preference("entity-001", Channel.EMAIL, NotificationCategory.PAYMENT, True)
    pref = await store.get("entity-001", Channel.EMAIL, NotificationCategory.PAYMENT)
    assert pref is not None
    assert pref.opt_in is True


@pytest.mark.asyncio
async def test_set_preference_returns_notification_preference() -> None:
    manager = _make_manager()
    from services.notification_hub.models import NotificationPreference

    pref = await manager.set_preference("entity-001", Channel.SMS, NotificationCategory.KYC, True)
    assert isinstance(pref, NotificationPreference)
    assert pref.entity_id == "entity-001"


@pytest.mark.asyncio
async def test_set_preference_opt_out_security_reflects_in_is_opted_in() -> None:
    manager = _make_manager()
    await manager.set_preference("entity-002", Channel.PUSH, NotificationCategory.SECURITY, False)
    result = await manager.is_opted_in("entity-002", Channel.PUSH, NotificationCategory.SECURITY)
    assert result is False


# ─── get_preferences() tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_preferences_returns_list() -> None:
    manager = _make_manager()
    await manager.set_preference("entity-001", Channel.EMAIL, NotificationCategory.PAYMENT, True)
    await manager.set_preference("entity-001", Channel.SMS, NotificationCategory.KYC, False)
    prefs = await manager.get_preferences("entity-001")
    assert len(prefs) == 2


@pytest.mark.asyncio
async def test_get_preferences_empty_for_unknown_entity() -> None:
    manager = _make_manager()
    prefs = await manager.get_preferences("unknown-entity")
    assert prefs == []


# ─── opt_out_all() tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_opt_out_all_sets_all_to_opt_out() -> None:
    manager = _make_manager()
    await manager.opt_out_all("entity-001")
    # SECURITY and OPERATIONAL should now be opted out
    sec = await manager.is_opted_in("entity-001", Channel.EMAIL, NotificationCategory.SECURITY)
    op = await manager.is_opted_in("entity-001", Channel.SMS, NotificationCategory.OPERATIONAL)
    assert sec is False
    assert op is False


@pytest.mark.asyncio
async def test_opt_out_all_returns_positive_count() -> None:
    manager = _make_manager()
    count = await manager.opt_out_all("entity-001")
    assert count > 0
    # 5 channels × 7 categories = 35
    assert count == 35


# ─── Entity independence tests ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_two_entities_independent_preferences() -> None:
    manager = _make_manager()
    await manager.set_preference("entity-A", Channel.EMAIL, NotificationCategory.MARKETING, True)
    await manager.set_preference("entity-B", Channel.EMAIL, NotificationCategory.MARKETING, False)
    a_result = await manager.is_opted_in("entity-A", Channel.EMAIL, NotificationCategory.MARKETING)
    b_result = await manager.is_opted_in("entity-B", Channel.EMAIL, NotificationCategory.MARKETING)
    assert a_result is True
    assert b_result is False


@pytest.mark.asyncio
async def test_set_preference_updates_existing_preference() -> None:
    manager = _make_manager()
    await manager.set_preference("entity-001", Channel.EMAIL, NotificationCategory.PAYMENT, True)
    await manager.set_preference("entity-001", Channel.EMAIL, NotificationCategory.PAYMENT, False)
    result = await manager.is_opted_in("entity-001", Channel.EMAIL, NotificationCategory.PAYMENT)
    assert result is False
