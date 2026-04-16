"""
tests/test_open_banking/test_consent_manager.py
IL-OBK-01 | Phase 15 — ConsentManager lifecycle tests.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from services.open_banking.consent_manager import ConsentManager
from services.open_banking.models import (
    AccountAccessType,
    ConsentStatus,
    ConsentType,
    InMemoryASPSPRegistry,
    InMemoryConsentStore,
    InMemoryOBAuditTrail,
)


def _make_manager(store=None, registry=None, audit=None):
    return ConsentManager(
        store=store or InMemoryConsentStore(),
        registry=registry or InMemoryASPSPRegistry(),
        audit=audit or InMemoryOBAuditTrail(),
    )


# ── create_consent ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_consent_status_awaiting():
    mgr = _make_manager()
    c = await mgr.create_consent(
        "ent-1", "barclays-uk", ConsentType.AISP, [AccountAccessType.ACCOUNTS], actor="test"
    )
    assert c.status == ConsentStatus.AWAITING_AUTHORISATION


@pytest.mark.asyncio
async def test_create_consent_creates_audit_entry():
    audit = InMemoryOBAuditTrail()
    mgr = _make_manager(audit=audit)
    await mgr.create_consent(
        "ent-1", "barclays-uk", ConsentType.AISP, [AccountAccessType.ACCOUNTS], actor="test"
    )
    events = await audit.list_events(event_type="consent.created")
    assert len(events) == 1


@pytest.mark.asyncio
async def test_create_consent_aspsp_not_found():
    mgr = _make_manager()
    with pytest.raises(ValueError, match="ASPSP not found"):
        await mgr.create_consent(
            "ent-1", "no-such-bank", ConsentType.AISP, [AccountAccessType.ACCOUNTS], actor="test"
        )


@pytest.mark.asyncio
async def test_create_consent_expires_in_90_days():
    mgr = _make_manager()
    before = datetime.now(UTC)
    c = await mgr.create_consent(
        "ent-1", "barclays-uk", ConsentType.AISP, [AccountAccessType.ACCOUNTS], actor="test"
    )
    after = datetime.now(UTC)
    expected_lower = before + timedelta(days=89, hours=23)
    expected_upper = after + timedelta(days=90, hours=1)
    assert expected_lower < c.expires_at < expected_upper


# ── authorise_consent ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_authorise_consent_success():
    mgr = _make_manager()
    c = await mgr.create_consent(
        "ent-1", "barclays-uk", ConsentType.AISP, [AccountAccessType.ACCOUNTS], actor="test"
    )
    updated = await mgr.authorise_consent(c.id, auth_code="CODE123", actor="test")
    assert updated.status == ConsentStatus.AUTHORISED


@pytest.mark.asyncio
async def test_authorise_consent_not_found():
    mgr = _make_manager()
    with pytest.raises(ValueError, match="Consent not found"):
        await mgr.authorise_consent("no-such-id", "CODE", "test")


@pytest.mark.asyncio
async def test_authorise_consent_already_authorised():
    mgr = _make_manager()
    c = await mgr.create_consent(
        "ent-1", "barclays-uk", ConsentType.AISP, [AccountAccessType.ACCOUNTS], actor="test"
    )
    await mgr.authorise_consent(c.id, "CODE", "test")
    with pytest.raises(ValueError, match="already authorised"):
        await mgr.authorise_consent(c.id, "CODE", "test")


@pytest.mark.asyncio
async def test_authorise_revoked_consent_raises():
    mgr = _make_manager()
    c = await mgr.create_consent(
        "ent-1", "barclays-uk", ConsentType.AISP, [AccountAccessType.ACCOUNTS], actor="test"
    )
    await mgr.revoke_consent(c.id, "test")
    with pytest.raises(ValueError):
        await mgr.authorise_consent(c.id, "CODE", "test")


@pytest.mark.asyncio
async def test_authorise_consent_creates_audit_entry():
    audit = InMemoryOBAuditTrail()
    mgr = _make_manager(audit=audit)
    c = await mgr.create_consent(
        "ent-1", "barclays-uk", ConsentType.AISP, [AccountAccessType.ACCOUNTS], actor="test"
    )
    await mgr.authorise_consent(c.id, "CODE", "test")
    events = await audit.list_events(event_type="consent.authorised")
    assert len(events) == 1


# ── revoke_consent ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_revoke_consent_success():
    mgr = _make_manager()
    c = await mgr.create_consent(
        "ent-1", "barclays-uk", ConsentType.AISP, [AccountAccessType.ACCOUNTS], actor="test"
    )
    updated = await mgr.revoke_consent(c.id, "test")
    assert updated.status == ConsentStatus.REVOKED


@pytest.mark.asyncio
async def test_revoke_consent_not_found():
    mgr = _make_manager()
    with pytest.raises(ValueError, match="Consent not found"):
        await mgr.revoke_consent("no-such-id", "test")


@pytest.mark.asyncio
async def test_revoke_consent_already_revoked():
    mgr = _make_manager()
    c = await mgr.create_consent(
        "ent-1", "barclays-uk", ConsentType.AISP, [AccountAccessType.ACCOUNTS], actor="test"
    )
    await mgr.revoke_consent(c.id, "test")
    with pytest.raises(ValueError, match="already revoked"):
        await mgr.revoke_consent(c.id, "test")


@pytest.mark.asyncio
async def test_revoke_consent_creates_audit_entry():
    audit = InMemoryOBAuditTrail()
    mgr = _make_manager(audit=audit)
    c = await mgr.create_consent(
        "ent-1", "barclays-uk", ConsentType.AISP, [AccountAccessType.ACCOUNTS], actor="test"
    )
    await mgr.revoke_consent(c.id, "test")
    events = await audit.list_events(event_type="consent.revoked")
    assert len(events) == 1


# ── get_consent / list_consents ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_consent_existing():
    mgr = _make_manager()
    c = await mgr.create_consent(
        "ent-1", "barclays-uk", ConsentType.AISP, [AccountAccessType.ACCOUNTS], actor="test"
    )
    result = await mgr.get_consent(c.id)
    assert result is not None
    assert result.id == c.id


@pytest.mark.asyncio
async def test_get_consent_missing_returns_none():
    mgr = _make_manager()
    result = await mgr.get_consent("ghost-id")
    assert result is None


@pytest.mark.asyncio
async def test_list_consents_returns_all_for_entity():
    mgr = _make_manager()
    for _ in range(3):
        await mgr.create_consent(
            "ent-X", "barclays-uk", ConsentType.AISP, [AccountAccessType.ACCOUNTS], actor="test"
        )
    results = await mgr.list_consents("ent-X")
    assert len(results) == 3


# ── is_valid ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_is_valid_authorised_not_expired():
    mgr = _make_manager()
    c = await mgr.create_consent(
        "ent-1", "barclays-uk", ConsentType.AISP, [AccountAccessType.ACCOUNTS], actor="test"
    )
    await mgr.authorise_consent(c.id, "CODE", "test")
    assert await mgr.is_valid(c.id) is True


@pytest.mark.asyncio
async def test_is_valid_not_authorised():
    mgr = _make_manager()
    c = await mgr.create_consent(
        "ent-1", "barclays-uk", ConsentType.AISP, [AccountAccessType.ACCOUNTS], actor="test"
    )
    assert await mgr.is_valid(c.id) is False


@pytest.mark.asyncio
async def test_is_valid_expired():
    store = InMemoryConsentStore()
    mgr = _make_manager(store=store)
    c = await mgr.create_consent(
        "ent-1", "barclays-uk", ConsentType.AISP, [AccountAccessType.ACCOUNTS], actor="test"
    )
    await mgr.authorise_consent(c.id, "CODE", "test")
    # Manually expire by updating expires_at to the past
    past = datetime(2000, 1, 1, tzinfo=UTC)
    await store.update_status(c.id, ConsentStatus.AUTHORISED, expires_at=past)
    assert await mgr.is_valid(c.id) is False


# ── Additional scenarios ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_multiple_consents_same_entity():
    mgr = _make_manager()
    c1 = await mgr.create_consent(
        "ent-1", "barclays-uk", ConsentType.AISP, [AccountAccessType.ACCOUNTS], actor="test"
    )
    c2 = await mgr.create_consent(
        "ent-1", "hsbc-uk", ConsentType.PISP, [AccountAccessType.ACCOUNTS], actor="test"
    )
    all_c = await mgr.list_consents("ent-1")
    ids = {c.id for c in all_c}
    assert c1.id in ids
    assert c2.id in ids


@pytest.mark.asyncio
async def test_consent_permissions_round_trip():
    mgr = _make_manager()
    perms = [AccountAccessType.ACCOUNTS, AccountAccessType.BALANCES, AccountAccessType.TRANSACTIONS]
    c = await mgr.create_consent("ent-1", "barclays-uk", ConsentType.AISP, perms, actor="test")
    assert c.permissions == perms


@pytest.mark.asyncio
async def test_create_consent_pisp_type():
    mgr = _make_manager()
    c = await mgr.create_consent(
        "ent-1", "barclays-uk", ConsentType.PISP, [AccountAccessType.ACCOUNTS], actor="test"
    )
    assert c.type == ConsentType.PISP


@pytest.mark.asyncio
async def test_create_consent_with_redirect_uri():
    mgr = _make_manager()
    c = await mgr.create_consent(
        "ent-1",
        "barclays-uk",
        ConsentType.AISP,
        [AccountAccessType.ACCOUNTS],
        actor="test",
        redirect_uri="https://example.com/cb",
    )
    assert c.redirect_uri == "https://example.com/cb"


@pytest.mark.asyncio
async def test_concurrent_creates_same_entity():
    mgr = _make_manager()
    tasks = [
        mgr.create_consent(
            "ent-1", "barclays-uk", ConsentType.AISP, [AccountAccessType.ACCOUNTS], actor="test"
        )
        for _ in range(5)
    ]
    consents = await asyncio.gather(*tasks)
    assert len({c.id for c in consents}) == 5


@pytest.mark.asyncio
async def test_full_lifecycle_create_authorise_revoke():
    mgr = _make_manager()
    c = await mgr.create_consent(
        "ent-1", "barclays-uk", ConsentType.AISP, [AccountAccessType.ACCOUNTS], actor="test"
    )
    assert c.status == ConsentStatus.AWAITING_AUTHORISATION

    authorised = await mgr.authorise_consent(c.id, "CODE", "test")
    assert authorised.status == ConsentStatus.AUTHORISED

    revoked = await mgr.revoke_consent(c.id, "test")
    assert revoked.status == ConsentStatus.REVOKED
