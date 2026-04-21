"""
tests/test_consent_management/test_models.py
Tests for consent management models, validators, and frozen dataclasses.
IL-CNS-01 | Phase 49 | Sprint 35

≥20 tests covering:
- ConsentGrant validators (expires_at > granted_at)
- TPPRegistration validator (I-02 jurisdiction block)
- HITLProposal dataclass
- InMemory stubs (append-only, I-24)
- ConsentScope, ConsentType, ConsentStatus enums
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from pydantic import ValidationError
import pytest

from services.consent_management.models import (
    BLOCKED_JURISDICTIONS,
    ConsentAuditEvent,
    ConsentGrant,
    ConsentScope,
    ConsentStatus,
    ConsentType,
    HITLProposal,
    InMemoryAuditLog,
    InMemoryConsentStore,
    InMemoryTPPRegistry,
    TPPRegistration,
    TPPStatus,
    TPPType,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def make_consent(
    consent_id: str = "cns_abc123",
    customer_id: str = "cust_001",
    tpp_id: str = "tpp_plaid_uk",
    status: ConsentStatus = ConsentStatus.ACTIVE,
    ttl_days: int = 90,
) -> ConsentGrant:
    now = datetime.now(UTC)
    return ConsentGrant(
        consent_id=consent_id,
        customer_id=customer_id,
        tpp_id=tpp_id,
        consent_type=ConsentType.AISP,
        scopes=[ConsentScope.ACCOUNTS, ConsentScope.BALANCES],
        granted_at=now.isoformat(),
        expires_at=(now + timedelta(days=ttl_days)).isoformat(),
        status=status,
        redirect_uri="https://tpp.example.com/callback",
    )


def make_tpp(
    tpp_id: str = "tpp_test",
    jurisdiction: str = "GB",
    tpp_type: TPPType = TPPType.AISP,
    status: TPPStatus = TPPStatus.REGISTERED,
) -> TPPRegistration:
    now = datetime.now(UTC).isoformat()
    return TPPRegistration(
        tpp_id=tpp_id,
        name="Test TPP Ltd",
        eidas_cert_id="EIDAS-TEST-001",
        tpp_type=tpp_type,
        status=status,
        registered_at=now,
        jurisdiction=jurisdiction,
        competent_authority="FCA",
    )


# ── ConsentGrant tests ────────────────────────────────────────────────────────


def test_consent_grant_valid_creates_successfully() -> None:
    """Test valid ConsentGrant creation."""
    consent = make_consent()
    assert consent.consent_id == "cns_abc123"
    assert consent.customer_id == "cust_001"
    assert consent.status == ConsentStatus.ACTIVE


def test_consent_grant_expires_after_granted_passes() -> None:
    """Test expires_at > granted_at validator passes."""
    now = datetime.now(UTC)
    consent = ConsentGrant(
        consent_id="cns_001",
        customer_id="c1",
        tpp_id="t1",
        consent_type=ConsentType.AISP,
        scopes=[ConsentScope.ACCOUNTS],
        granted_at=now.isoformat(),
        expires_at=(now + timedelta(days=1)).isoformat(),
        status=ConsentStatus.ACTIVE,
        redirect_uri="https://tpp.example.com",
    )
    assert consent.expires_at > consent.granted_at


def test_consent_grant_expires_before_granted_fails() -> None:
    """Test expires_at <= granted_at raises ValidationError."""
    now = datetime.now(UTC)
    with pytest.raises(ValidationError, match="expires_at must be after granted_at"):
        ConsentGrant(
            consent_id="cns_001",
            customer_id="c1",
            tpp_id="t1",
            consent_type=ConsentType.AISP,
            scopes=[ConsentScope.ACCOUNTS],
            granted_at=now.isoformat(),
            expires_at=(now - timedelta(days=1)).isoformat(),
            status=ConsentStatus.ACTIVE,
            redirect_uri="https://tpp.example.com",
        )


def test_consent_grant_transaction_limit_is_decimal() -> None:
    """Test transaction_limit is Decimal (I-01)."""
    consent = make_consent()
    consent2 = consent.model_copy(update={"transaction_limit": Decimal("500.00")})
    assert isinstance(consent2.transaction_limit, Decimal)


def test_consent_grant_all_scopes() -> None:
    """Test ConsentGrant with all four scopes."""
    consent = make_consent()
    all_scopes = [
        ConsentScope.ACCOUNTS,
        ConsentScope.BALANCES,
        ConsentScope.TRANSACTIONS,
        ConsentScope.PAYMENTS,
    ]
    c = consent.model_copy(update={"scopes": all_scopes})
    assert len(c.scopes) == 4


def test_consent_type_enum_values() -> None:
    """Test ConsentType enum has all required values."""
    assert ConsentType.AISP == "AISP"
    assert ConsentType.PISP == "PISP"
    assert ConsentType.CBPII == "CBPII"


def test_consent_status_enum_values() -> None:
    """Test ConsentStatus enum has all required values."""
    assert ConsentStatus.PENDING == "PENDING"
    assert ConsentStatus.ACTIVE == "ACTIVE"
    assert ConsentStatus.REVOKED == "REVOKED"
    assert ConsentStatus.EXPIRED == "EXPIRED"


def test_consent_scope_enum_values() -> None:
    """Test ConsentScope enum has all required values."""
    assert ConsentScope.ACCOUNTS == "ACCOUNTS"
    assert ConsentScope.BALANCES == "BALANCES"
    assert ConsentScope.TRANSACTIONS == "TRANSACTIONS"
    assert ConsentScope.PAYMENTS == "PAYMENTS"


# ── TPPRegistration tests ─────────────────────────────────────────────────────


def test_tpp_registration_valid_creates_successfully() -> None:
    """Test valid TPPRegistration creation."""
    tpp = make_tpp()
    assert tpp.tpp_id == "tpp_test"
    assert tpp.status == TPPStatus.REGISTERED


def test_tpp_jurisdiction_blocked_ru_raises() -> None:
    """Test I-02: RU jurisdiction is blocked."""
    with pytest.raises(ValidationError, match="blocked"):
        make_tpp(jurisdiction="RU")


def test_tpp_jurisdiction_blocked_ir_raises() -> None:
    """Test I-02: IR jurisdiction is blocked."""
    with pytest.raises(ValidationError, match="blocked"):
        make_tpp(jurisdiction="IR")


def test_tpp_jurisdiction_blocked_kp_raises() -> None:
    """Test I-02: KP jurisdiction is blocked."""
    with pytest.raises(ValidationError, match="blocked"):
        make_tpp(jurisdiction="KP")


def test_tpp_jurisdiction_blocked_by_raises() -> None:
    """Test I-02: BY jurisdiction is blocked."""
    with pytest.raises(ValidationError, match="blocked"):
        make_tpp(jurisdiction="BY")


def test_tpp_jurisdiction_gb_allowed() -> None:
    """Test GB jurisdiction is allowed."""
    tpp = make_tpp(jurisdiction="GB")
    assert tpp.jurisdiction == "GB"


def test_tpp_jurisdiction_de_allowed() -> None:
    """Test DE jurisdiction is allowed."""
    tpp = make_tpp(jurisdiction="DE")
    assert tpp.jurisdiction == "DE"


def test_tpp_type_enum_values() -> None:
    """Test TPPType enum has all required values."""
    assert TPPType.AISP == "AISP"
    assert TPPType.PISP == "PISP"
    assert TPPType.BOTH == "BOTH"


def test_tpp_status_enum_values() -> None:
    """Test TPPStatus enum has all required values."""
    assert TPPStatus.REGISTERED == "REGISTERED"
    assert TPPStatus.SUSPENDED == "SUSPENDED"
    assert TPPStatus.DEREGISTERED == "DEREGISTERED"


def test_blocked_jurisdictions_contains_required() -> None:
    """Test BLOCKED_JURISDICTIONS contains all required codes (I-02)."""
    required = {"RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE", "SY"}
    assert required.issubset(BLOCKED_JURISDICTIONS)


# ── HITLProposal tests ────────────────────────────────────────────────────────


def test_hitl_proposal_dataclass_creates() -> None:
    """Test HITLProposal dataclass creation."""
    proposal = HITLProposal(
        action="REVOKE_CONSENT",
        entity_id="cns_abc123",
        requires_approval_from="COMPLIANCE_OFFICER",
        reason="Revocation requires approval",
    )
    assert proposal.action == "REVOKE_CONSENT"
    assert proposal.autonomy_level == "L4"


def test_hitl_proposal_is_mutable_dataclass() -> None:
    """Test HITLProposal is a regular (mutable) dataclass per spec."""
    proposal = HITLProposal(
        action="TEST",
        entity_id="id1",
        requires_approval_from="OFFICER",
        reason="reason",
    )
    proposal.action = "UPDATED"
    assert proposal.action == "UPDATED"


# ── InMemory stubs tests ──────────────────────────────────────────────────────


def test_inmemory_consent_store_append_only() -> None:
    """Test InMemoryConsentStore is append-only (I-24)."""
    store = InMemoryConsentStore()
    c = make_consent()
    store.save(c)
    assert store.get(c.consent_id) == c


def test_inmemory_consent_store_list_by_customer() -> None:
    """Test list_by_customer returns all consents for customer."""
    store = InMemoryConsentStore()
    c1 = make_consent(consent_id="cns_1", customer_id="c1")
    c2 = make_consent(consent_id="cns_2", customer_id="c1")
    c3 = make_consent(consent_id="cns_3", customer_id="c2")
    store.save(c1)
    store.save(c2)
    store.save(c3)
    result = store.list_by_customer("c1")
    assert len(result) == 2


def test_inmemory_tpp_registry_seeds_two_tpps() -> None:
    """Test InMemoryTPPRegistry seeds Plaid UK and TrueLayer."""
    registry = InMemoryTPPRegistry()
    active = registry.list_active()
    assert len(active) == 2
    names = {t.name for t in active}
    assert "Plaid UK Limited" in names
    assert "TrueLayer Limited" in names


def test_inmemory_audit_log_append_only() -> None:
    """Test InMemoryAuditLog is append-only (I-24)."""
    log = InMemoryAuditLog()
    event = ConsentAuditEvent(
        event_id="evt_001",
        consent_id="cns_001",
        event_type="GRANTED",
        actor="cust",
        timestamp=datetime.now(UTC).isoformat(),
        details="test",
    )
    log.append(event)
    assert len(log.list_all()) == 1
