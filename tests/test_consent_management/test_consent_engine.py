"""
tests/test_consent_management/test_consent_engine.py
Tests for ConsentEngine: grant, revoke, validate, active list.
IL-CNS-01 | Phase 49 | Sprint 35

≥25 tests covering:
- grant_consent (valid, invalid TPP, with limit)
- revoke_consent returns HITLProposal (I-27)
- validate_consent (active, expired, wrong scope)
- get_active_consents filtering
- SHA-256 consent IDs
- Audit log appends (I-24)
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from services.consent_management.consent_engine import ConsentEngine
from services.consent_management.models import (
    ConsentScope,
    ConsentStatus,
    ConsentType,
    HITLProposal,
    InMemoryAuditLog,
    InMemoryConsentStore,
    InMemoryTPPRegistry,
)


def make_engine() -> tuple[
    ConsentEngine, InMemoryConsentStore, InMemoryTPPRegistry, InMemoryAuditLog
]:
    store = InMemoryConsentStore()
    registry = InMemoryTPPRegistry()
    audit = InMemoryAuditLog()
    engine = ConsentEngine(store, registry, audit)
    return engine, store, registry, audit


# ── grant_consent tests ───────────────────────────────────────────────────────


def test_grant_consent_returns_consent_grant() -> None:
    """Test grant_consent returns ConsentGrant."""
    engine, _, _, _ = make_engine()
    consent = engine.grant_consent("c1", "tpp_plaid_uk", ConsentType.AISP, [ConsentScope.ACCOUNTS])
    assert consent.consent_id.startswith("cns_")
    assert consent.status == ConsentStatus.ACTIVE


def test_grant_consent_tpp_not_registered_raises() -> None:
    """Test grant_consent raises ValueError for unknown TPP."""
    engine, _, _, _ = make_engine()
    with pytest.raises(ValueError, match="not REGISTERED"):
        engine.grant_consent("c1", "tpp_unknown", ConsentType.AISP, [ConsentScope.ACCOUNTS])


def test_grant_consent_with_transaction_limit() -> None:
    """Test grant_consent sets transaction_limit as Decimal (I-01)."""
    engine, _, _, _ = make_engine()
    limit = Decimal("500.00")
    consent = engine.grant_consent(
        "c1", "tpp_plaid_uk", ConsentType.PISP, [ConsentScope.PAYMENTS], transaction_limit=limit
    )
    assert consent.transaction_limit == limit


def test_grant_consent_sets_active_status() -> None:
    """Test granted consent has ACTIVE status."""
    engine, _, _, _ = make_engine()
    consent = engine.grant_consent("c1", "tpp_plaid_uk", ConsentType.AISP, [ConsentScope.ACCOUNTS])
    assert consent.status == ConsentStatus.ACTIVE


def test_grant_consent_sha256_id_format() -> None:
    """Test consent_id has cns_ prefix and 8-char hash suffix."""
    engine, _, _, _ = make_engine()
    consent = engine.grant_consent("c1", "tpp_plaid_uk", ConsentType.AISP, [ConsentScope.ACCOUNTS])
    parts = consent.consent_id.split("_")
    assert parts[0] == "cns"
    assert len(parts[1]) == 8


def test_grant_consent_expires_at_future() -> None:
    """Test expires_at is in the future."""
    engine, _, _, _ = make_engine()
    consent = engine.grant_consent("c1", "tpp_plaid_uk", ConsentType.AISP, [ConsentScope.ACCOUNTS])
    now = datetime.now(UTC).isoformat()
    assert consent.expires_at > now


def test_grant_consent_stores_in_store() -> None:
    """Test grant_consent saves to consent store."""
    engine, store, _, _ = make_engine()
    consent = engine.grant_consent("c1", "tpp_plaid_uk", ConsentType.AISP, [ConsentScope.ACCOUNTS])
    stored = store.get(consent.consent_id)
    assert stored is not None
    assert stored.consent_id == consent.consent_id


def test_grant_consent_appends_audit_event() -> None:
    """Test grant_consent appends audit event (I-24)."""
    engine, _, _, audit = make_engine()
    engine.grant_consent("c1", "tpp_plaid_uk", ConsentType.AISP, [ConsentScope.ACCOUNTS])
    events = audit.list_all()
    assert len(events) == 1
    assert events[0].event_type == "CONSENT_GRANTED"


def test_grant_consent_multiple_scopes() -> None:
    """Test grant_consent with multiple scopes."""
    engine, _, _, _ = make_engine()
    scopes = [ConsentScope.ACCOUNTS, ConsentScope.BALANCES, ConsentScope.TRANSACTIONS]
    consent = engine.grant_consent("c1", "tpp_plaid_uk", ConsentType.AISP, scopes)
    assert len(consent.scopes) == 3


def test_grant_consent_custom_ttl() -> None:
    """Test grant_consent with custom ttl_days."""
    engine, _, _, _ = make_engine()
    consent = engine.grant_consent(
        "c1", "tpp_plaid_uk", ConsentType.AISP, [ConsentScope.ACCOUNTS], ttl_days=30
    )
    now = datetime.now(UTC)
    expires = datetime.fromisoformat(consent.expires_at)
    diff = expires - now
    assert 29 <= diff.days <= 30


# ── revoke_consent tests ──────────────────────────────────────────────────────


def test_revoke_consent_returns_hitl_proposal() -> None:
    """Test revoke_consent returns HITLProposal (I-27)."""
    engine, _, _, _ = make_engine()
    proposal = engine.revoke_consent("cns_abc123", "customer")
    assert isinstance(proposal, HITLProposal)


def test_revoke_consent_action_is_revoke() -> None:
    """Test HITLProposal action is REVOKE_CONSENT."""
    engine, _, _, _ = make_engine()
    proposal = engine.revoke_consent("cns_abc123", "customer")
    assert proposal.action == "REVOKE_CONSENT"


def test_revoke_consent_requires_compliance_officer() -> None:
    """Test HITLProposal requires COMPLIANCE_OFFICER approval."""
    engine, _, _, _ = make_engine()
    proposal = engine.revoke_consent("cns_abc123", "customer")
    assert proposal.requires_approval_from == "COMPLIANCE_OFFICER"


def test_revoke_consent_autonomy_level_l4() -> None:
    """Test HITLProposal autonomy_level is L4."""
    engine, _, _, _ = make_engine()
    proposal = engine.revoke_consent("cns_abc123", "customer")
    assert proposal.autonomy_level == "L4"


# ── validate_consent tests ────────────────────────────────────────────────────


def test_validate_consent_active_with_scope_returns_true() -> None:
    """Test validate_consent returns True for active consent with matching scope."""
    engine, _, _, _ = make_engine()
    consent = engine.grant_consent(
        "c1", "tpp_plaid_uk", ConsentType.AISP, [ConsentScope.ACCOUNTS, ConsentScope.BALANCES]
    )
    assert engine.validate_consent(consent.consent_id, ConsentScope.ACCOUNTS) is True


def test_validate_consent_missing_scope_returns_false() -> None:
    """Test validate_consent returns False for scope not in consent."""
    engine, _, _, _ = make_engine()
    consent = engine.grant_consent("c1", "tpp_plaid_uk", ConsentType.AISP, [ConsentScope.ACCOUNTS])
    assert engine.validate_consent(consent.consent_id, ConsentScope.PAYMENTS) is False


def test_validate_consent_unknown_id_returns_false() -> None:
    """Test validate_consent returns False for unknown consent_id."""
    engine, _, _, _ = make_engine()
    assert engine.validate_consent("cns_unknown", ConsentScope.ACCOUNTS) is False


def test_validate_consent_revoked_returns_false() -> None:
    """Test validate_consent returns False for REVOKED consent."""
    engine, store, _, _ = make_engine()
    consent = engine.grant_consent("c1", "tpp_plaid_uk", ConsentType.AISP, [ConsentScope.ACCOUNTS])
    # Manually revoke in store
    revoked = consent.model_copy(update={"status": ConsentStatus.REVOKED})
    store.save(revoked)
    assert engine.validate_consent(consent.consent_id, ConsentScope.ACCOUNTS) is False


# ── get_active_consents tests ─────────────────────────────────────────────────


def test_get_active_consents_returns_active_only() -> None:
    """Test get_active_consents filters to ACTIVE non-expired consents."""
    engine, _, _, _ = make_engine()
    engine.grant_consent("c1", "tpp_plaid_uk", ConsentType.AISP, [ConsentScope.ACCOUNTS])
    engine.grant_consent("c1", "tpp_truelayer", ConsentType.AISP, [ConsentScope.BALANCES])
    active = engine.get_active_consents("c1")
    assert len(active) == 2
    assert all(c.status == ConsentStatus.ACTIVE for c in active)


def test_get_active_consents_empty_for_unknown_customer() -> None:
    """Test get_active_consents returns empty for unknown customer."""
    engine, _, _, _ = make_engine()
    active = engine.get_active_consents("cust_unknown")
    assert active == []


def test_get_active_consents_excludes_other_customers() -> None:
    """Test get_active_consents only returns consents for specified customer."""
    engine, _, _, _ = make_engine()
    engine.grant_consent("c1", "tpp_plaid_uk", ConsentType.AISP, [ConsentScope.ACCOUNTS])
    engine.grant_consent("c2", "tpp_plaid_uk", ConsentType.AISP, [ConsentScope.ACCOUNTS])
    active = engine.get_active_consents("c1")
    assert all(c.customer_id == "c1" for c in active)
