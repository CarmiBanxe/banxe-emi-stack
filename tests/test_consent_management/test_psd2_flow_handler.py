"""
tests/test_consent_management/test_psd2_flow_handler.py
Tests for PSD2FlowHandler: AISP flow, PISP HITL, CBPII EDD threshold.
IL-CNS-01 | Phase 49 | Sprint 35

≥20 tests covering:
- initiate_aisp_flow (pending state, unknown TPP)
- complete_aisp_flow (approved → ACTIVE, declined → REVOKED)
- initiate_pisp_payment returns HITLProposal (I-27)
- handle_cbpii_check (valid, expired, EDD threshold raises)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from services.consent_management.models import (
    ConsentGrant,
    ConsentScope,
    ConsentStatus,
    ConsentType,
    HITLProposal,
    InMemoryAuditLog,
    InMemoryConsentStore,
    InMemoryTPPRegistry,
)
from services.consent_management.psd2_flow_handler import EDD_THRESHOLD, PSD2FlowHandler


def make_handler() -> tuple[
    PSD2FlowHandler, InMemoryConsentStore, InMemoryTPPRegistry, InMemoryAuditLog
]:
    store = InMemoryConsentStore()
    registry = InMemoryTPPRegistry()
    audit = InMemoryAuditLog()
    handler = PSD2FlowHandler(store, registry, audit)
    return handler, store, registry, audit


# ── initiate_aisp_flow tests ──────────────────────────────────────────────────


def test_initiate_aisp_flow_returns_pending_consent() -> None:
    """Test AISP flow initiation creates PENDING consent."""
    handler, _, _, _ = make_handler()
    consent = handler.initiate_aisp_flow(
        "c1", "tpp_plaid_uk", [ConsentScope.ACCOUNTS], "https://callback.example.com"
    )
    assert consent.status == ConsentStatus.PENDING


def test_initiate_aisp_flow_consent_type_is_aisp() -> None:
    """Test AISP flow creates AISP consent type."""
    handler, _, _, _ = make_handler()
    consent = handler.initiate_aisp_flow(
        "c1", "tpp_plaid_uk", [ConsentScope.ACCOUNTS], "https://callback.example.com"
    )
    assert consent.consent_type == ConsentType.AISP


def test_initiate_aisp_flow_unknown_tpp_raises() -> None:
    """Test AISP flow raises ValueError for unregistered TPP."""
    handler, _, _, _ = make_handler()
    with pytest.raises(ValueError, match="not REGISTERED"):
        handler.initiate_aisp_flow(
            "c1", "tpp_unknown", [ConsentScope.ACCOUNTS], "https://callback.example.com"
        )


def test_initiate_aisp_flow_stores_consent() -> None:
    """Test AISP flow saves consent to store."""
    handler, store, _, _ = make_handler()
    consent = handler.initiate_aisp_flow(
        "c1", "tpp_plaid_uk", [ConsentScope.ACCOUNTS], "https://callback.example.com"
    )
    assert store.get(consent.consent_id) is not None


def test_initiate_aisp_flow_appends_audit_event() -> None:
    """Test AISP flow appends audit event (I-24)."""
    handler, _, _, audit = make_handler()
    handler.initiate_aisp_flow(
        "c1", "tpp_plaid_uk", [ConsentScope.ACCOUNTS], "https://callback.example.com"
    )
    events = audit.list_all()
    assert len(events) == 1
    assert events[0].event_type == "AISP_INITIATED"


# ── complete_aisp_flow tests ──────────────────────────────────────────────────


def test_complete_aisp_flow_approved_activates() -> None:
    """Test completing AISP flow with approval → ACTIVE."""
    handler, _, _, _ = make_handler()
    consent = handler.initiate_aisp_flow(
        "c1", "tpp_plaid_uk", [ConsentScope.ACCOUNTS], "https://example.com"
    )
    completed = handler.complete_aisp_flow(consent.consent_id, customer_approved=True)
    assert completed.status == ConsentStatus.ACTIVE


def test_complete_aisp_flow_rejected_revokes() -> None:
    """Test completing AISP flow with rejection → REVOKED."""
    handler, _, _, _ = make_handler()
    consent = handler.initiate_aisp_flow(
        "c1", "tpp_plaid_uk", [ConsentScope.ACCOUNTS], "https://example.com"
    )
    completed = handler.complete_aisp_flow(consent.consent_id, customer_approved=False)
    assert completed.status == ConsentStatus.REVOKED


def test_complete_aisp_flow_unknown_consent_raises() -> None:
    """Test complete_aisp_flow raises ValueError for unknown consent."""
    handler, _, _, _ = make_handler()
    with pytest.raises(ValueError, match="not found"):
        handler.complete_aisp_flow("cns_unknown", customer_approved=True)


def test_complete_aisp_flow_appends_audit_event() -> None:
    """Test completing AISP flow appends audit event (I-24)."""
    handler, _, _, audit = make_handler()
    consent = handler.initiate_aisp_flow(
        "c1", "tpp_plaid_uk", [ConsentScope.ACCOUNTS], "https://example.com"
    )
    handler.complete_aisp_flow(consent.consent_id, customer_approved=True)
    events = audit.list_all()
    assert len(events) == 2  # initiate + complete
    event_types = [e.event_type for e in events]
    assert "AISP_COMPLETED" in event_types


def test_complete_aisp_flow_rejected_appends_rejected_event() -> None:
    """Test rejecting AISP flow appends AISP_REJECTED event."""
    handler, _, _, audit = make_handler()
    consent = handler.initiate_aisp_flow(
        "c1", "tpp_plaid_uk", [ConsentScope.ACCOUNTS], "https://example.com"
    )
    handler.complete_aisp_flow(consent.consent_id, customer_approved=False)
    events = audit.list_all()
    event_types = [e.event_type for e in events]
    assert "AISP_REJECTED" in event_types


# ── initiate_pisp_payment tests ───────────────────────────────────────────────


def test_initiate_pisp_payment_returns_hitl_proposal() -> None:
    """Test PISP payment initiation always returns HITLProposal (I-27)."""
    handler, _, _, _ = make_handler()
    proposal = handler.initiate_pisp_payment("cns_001", Decimal("100.00"), "payee_001")
    assert isinstance(proposal, HITLProposal)


def test_initiate_pisp_payment_action_is_pisp() -> None:
    """Test PISP HITLProposal has correct action."""
    handler, _, _, _ = make_handler()
    proposal = handler.initiate_pisp_payment("cns_001", Decimal("100.00"), "payee_001")
    assert proposal.action == "INITIATE_PISP_PAYMENT"


def test_initiate_pisp_payment_requires_compliance_officer() -> None:
    """Test PISP proposal requires COMPLIANCE_OFFICER."""
    handler, _, _, _ = make_handler()
    proposal = handler.initiate_pisp_payment("cns_001", Decimal("1.00"), "payee")
    assert proposal.requires_approval_from == "COMPLIANCE_OFFICER"


def test_initiate_pisp_payment_autonomy_level_l4() -> None:
    """Test PISP proposal has L4 autonomy."""
    handler, _, _, _ = make_handler()
    proposal = handler.initiate_pisp_payment("cns_001", Decimal("1.00"), "payee")
    assert proposal.autonomy_level == "L4"


# ── handle_cbpii_check tests ──────────────────────────────────────────────────


def test_handle_cbpii_check_valid_consent_returns_true() -> None:
    """Test CBPII check returns True for valid amount and active consent."""
    handler, store, _, _ = make_handler()
    # Create active CBPII consent in store
    now = datetime.now(UTC)
    consent = ConsentGrant(
        consent_id="cns_cbpii",
        customer_id="c1",
        tpp_id="tpp_plaid_uk",
        consent_type=ConsentType.CBPII,
        scopes=[ConsentScope.ACCOUNTS],
        granted_at=now.isoformat(),
        expires_at=(now + timedelta(days=90)).isoformat(),
        status=ConsentStatus.ACTIVE,
        redirect_uri="https://example.com",
    )
    store.save(consent)
    result = handler.handle_cbpii_check("cns_cbpii", Decimal("999.99"))
    assert result is True


def test_handle_cbpii_check_edd_threshold_raises() -> None:
    """Test CBPII check raises ValueError for amount >= £10k (I-04)."""
    handler, _, _, _ = make_handler()
    with pytest.raises(ValueError, match="EDD threshold"):
        handler.handle_cbpii_check("cns_001", Decimal("10000"))


def test_handle_cbpii_check_exactly_at_threshold_raises() -> None:
    """Test CBPII check raises ValueError for amount == EDD threshold exactly."""
    handler, _, _, _ = make_handler()
    with pytest.raises(ValueError, match="EDD threshold"):
        handler.handle_cbpii_check("cns_001", EDD_THRESHOLD)


def test_handle_cbpii_check_above_threshold_raises() -> None:
    """Test CBPII check raises ValueError for amount > EDD threshold."""
    handler, _, _, _ = make_handler()
    with pytest.raises(ValueError, match="EDD threshold"):
        handler.handle_cbpii_check("cns_001", Decimal("50000"))


def test_handle_cbpii_check_unknown_consent_returns_false() -> None:
    """Test CBPII check returns False for unknown consent."""
    handler, _, _, _ = make_handler()
    result = handler.handle_cbpii_check("cns_unknown", Decimal("100"))
    assert result is False


def test_handle_cbpii_check_edd_threshold_value() -> None:
    """Test EDD_THRESHOLD is £10,000 (I-04)."""
    assert Decimal("10000") == EDD_THRESHOLD
