"""
tests/test_consent_management/test_tpp_registry.py
Tests for TPPRegistryService: register, suspend HITL, deregister HITL.
IL-CNS-01 | Phase 49 | Sprint 35

≥20 tests covering:
- register_tpp (valid, blocked jurisdiction I-02)
- get_tpp
- list_active_tpps (type filter)
- suspend_tpp returns HITLProposal (I-27)
- deregister_tpp returns HITLProposal (I-27)
- SHA-256 TPP IDs
"""

from __future__ import annotations

import pytest

from services.consent_management.models import (
    HITLProposal,
    InMemoryTPPRegistry,
    TPPStatus,
    TPPType,
)
from services.consent_management.tpp_registry import TPPRegistryService


def make_service() -> tuple[TPPRegistryService, InMemoryTPPRegistry]:
    registry = InMemoryTPPRegistry()
    svc = TPPRegistryService(registry)
    return svc, registry


# ── register_tpp tests ────────────────────────────────────────────────────────


def test_register_tpp_returns_registration() -> None:
    """Test register_tpp returns TPPRegistration."""
    svc, _ = make_service()
    tpp = svc.register_tpp("Test Bank", "EIDAS-001", TPPType.AISP, "GB", "FCA")
    assert tpp.name == "Test Bank"
    assert tpp.status == TPPStatus.REGISTERED


def test_register_tpp_sha256_id_format() -> None:
    """Test registered TPP has tpp_ prefix SHA-256 ID."""
    svc, _ = make_service()
    tpp = svc.register_tpp("Test Bank", "EIDAS-001", TPPType.AISP, "GB", "FCA")
    parts = tpp.tpp_id.split("_")
    assert parts[0] == "tpp"
    assert len(parts[1]) == 8


def test_register_tpp_blocked_ru_raises() -> None:
    """Test I-02: RU jurisdiction raises ValueError."""
    svc, _ = make_service()
    with pytest.raises(ValueError, match="blocked"):
        svc.register_tpp("Russian Bank", "EIDAS-RU-001", TPPType.AISP, "RU", "CBR")


def test_register_tpp_blocked_ir_raises() -> None:
    """Test I-02: IR jurisdiction raises ValueError."""
    svc, _ = make_service()
    with pytest.raises(ValueError, match="blocked"):
        svc.register_tpp("Iranian Bank", "EIDAS-IR-001", TPPType.PISP, "IR", "CBI")


def test_register_tpp_blocked_kp_raises() -> None:
    """Test I-02: KP jurisdiction raises ValueError."""
    svc, _ = make_service()
    with pytest.raises(ValueError, match="blocked"):
        svc.register_tpp("NK Bank", "EIDAS-KP-001", TPPType.BOTH, "KP", "CBC")


def test_register_tpp_blocked_by_raises() -> None:
    """Test I-02: BY jurisdiction raises ValueError."""
    svc, _ = make_service()
    with pytest.raises(ValueError, match="blocked"):
        svc.register_tpp("Belarus Bank", "EIDAS-BY-001", TPPType.AISP, "BY", "NBRB")


def test_register_tpp_all_types() -> None:
    """Test registering AISP, PISP, and BOTH type TPPs."""
    svc, _ = make_service()
    aisp = svc.register_tpp("AISP Co", "EIDAS-A-001", TPPType.AISP, "GB", "FCA")
    pisp = svc.register_tpp("PISP Co", "EIDAS-P-001", TPPType.PISP, "DE", "BaFin")
    both = svc.register_tpp("Both Co", "EIDAS-B-001", TPPType.BOTH, "FR", "ACPR")
    assert aisp.tpp_type == TPPType.AISP
    assert pisp.tpp_type == TPPType.PISP
    assert both.tpp_type == TPPType.BOTH


# ── get_tpp tests ─────────────────────────────────────────────────────────────


def test_get_tpp_returns_registered_tpp() -> None:
    """Test get_tpp returns registered TPP."""
    svc, _ = make_service()
    tpp = svc.register_tpp("Test Bank", "EIDAS-001", TPPType.AISP, "GB", "FCA")
    retrieved = svc.get_tpp(tpp.tpp_id)
    assert retrieved is not None
    assert retrieved.tpp_id == tpp.tpp_id


def test_get_tpp_returns_none_for_unknown() -> None:
    """Test get_tpp returns None for unknown ID."""
    svc, _ = make_service()
    result = svc.get_tpp("tpp_unknown")
    assert result is None


def test_get_tpp_seeded_plaid_uk() -> None:
    """Test seeded Plaid UK TPP is retrievable."""
    svc, _ = make_service()
    plaid = svc.get_tpp("tpp_plaid_uk")
    assert plaid is not None
    assert plaid.name == "Plaid UK Limited"


# ── list_active_tpps tests ────────────────────────────────────────────────────


def test_list_active_tpps_returns_seeded() -> None:
    """Test list_active_tpps returns seeded TPPs."""
    svc, _ = make_service()
    active = svc.list_active_tpps()
    assert len(active) == 2


def test_list_active_tpps_type_filter_aisp() -> None:
    """Test list_active_tpps filtered by AISP type."""
    svc, _ = make_service()
    aisp = svc.list_active_tpps(TPPType.AISP)
    # Plaid UK is AISP, TrueLayer is BOTH (should be included)
    assert any(t.name == "Plaid UK Limited" for t in aisp)


def test_list_active_tpps_includes_both_for_any_type() -> None:
    """Test BOTH type TPP appears in AISP and PISP filters."""
    svc, _ = make_service()
    # TrueLayer is BOTH
    aisp_list = svc.list_active_tpps(TPPType.AISP)
    pisp_list = svc.list_active_tpps(TPPType.PISP)
    assert any(t.name == "TrueLayer Limited" for t in aisp_list)
    assert any(t.name == "TrueLayer Limited" for t in pisp_list)


# ── suspend_tpp tests ─────────────────────────────────────────────────────────


def test_suspend_tpp_returns_hitl_proposal() -> None:
    """Test suspend_tpp returns HITLProposal (I-27)."""
    svc, _ = make_service()
    proposal = svc.suspend_tpp("tpp_plaid_uk", "regulatory review", "operator1")
    assert isinstance(proposal, HITLProposal)


def test_suspend_tpp_action_is_suspend() -> None:
    """Test HITLProposal action is SUSPEND_TPP."""
    svc, _ = make_service()
    proposal = svc.suspend_tpp("tpp_plaid_uk", "reason", "operator1")
    assert proposal.action == "SUSPEND_TPP"


def test_suspend_tpp_requires_compliance_officer() -> None:
    """Test HITLProposal requires COMPLIANCE_OFFICER."""
    svc, _ = make_service()
    proposal = svc.suspend_tpp("tpp_plaid_uk", "reason", "operator1")
    assert proposal.requires_approval_from == "COMPLIANCE_OFFICER"


def test_suspend_tpp_autonomy_level_l4() -> None:
    """Test HITLProposal autonomy_level is L4."""
    svc, _ = make_service()
    proposal = svc.suspend_tpp("tpp_plaid_uk", "reason", "operator1")
    assert proposal.autonomy_level == "L4"


# ── deregister_tpp tests ──────────────────────────────────────────────────────


def test_deregister_tpp_returns_hitl_proposal() -> None:
    """Test deregister_tpp returns HITLProposal (I-27)."""
    svc, _ = make_service()
    proposal = svc.deregister_tpp("tpp_plaid_uk", "voluntary", "operator1")
    assert isinstance(proposal, HITLProposal)


def test_deregister_tpp_action_is_deregister() -> None:
    """Test HITLProposal action is DEREGISTER_TPP."""
    svc, _ = make_service()
    proposal = svc.deregister_tpp("tpp_plaid_uk", "reason", "operator1")
    assert proposal.action == "DEREGISTER_TPP"


def test_deregister_tpp_autonomy_level_l4() -> None:
    """Test deregister HITLProposal has L4 autonomy."""
    svc, _ = make_service()
    proposal = svc.deregister_tpp("tpp_plaid_uk", "reason", "operator1")
    assert proposal.autonomy_level == "L4"
