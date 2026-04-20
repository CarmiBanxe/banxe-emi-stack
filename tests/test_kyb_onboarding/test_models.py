"""Tests for KYB models — Phase 45 (IL-KYB-01)."""

from __future__ import annotations

import dataclasses
from decimal import Decimal

import pytest

from services.kyb_onboarding.models import (
    BusinessApplication,
    BusinessType,
    DocumentType,
    HITLProposal,
    InMemoryApplicationStore,
    InMemoryKYBDecisionStore,
    InMemoryUBOStore,
    KYBDecision,
    KYBDocument,
    KYBRiskAssessment,
    KYBStatus,
    RiskTier,
    UBOVerification,
    UltimateBeneficialOwner,
)

# --- Enum values ---


def test_business_type_enum_values():
    assert BusinessType.LTD == "ltd"
    assert BusinessType.LLP == "llp"
    assert BusinessType.SOLE_TRADER == "sole_trader"
    assert BusinessType.PLC == "plc"
    assert BusinessType.PARTNERSHIP == "partnership"
    assert BusinessType.CHARITY == "charity"


def test_kyb_status_enum_values():
    assert KYBStatus.SUBMITTED == "submitted"
    assert KYBStatus.APPROVED == "approved"
    assert KYBStatus.REJECTED == "rejected"
    assert KYBStatus.SUSPENDED == "suspended"
    assert KYBStatus.DOCUMENTS_PENDING == "documents_pending"
    assert KYBStatus.UNDER_REVIEW == "under_review"


def test_ubo_verification_enum_values():
    assert UBOVerification.PENDING == "pending"
    assert UBOVerification.VERIFIED == "verified"
    assert UBOVerification.FAILED == "failed"
    assert UBOVerification.EXEMPTED == "exempted"


def test_risk_tier_enum_values():
    assert RiskTier.LOW == "low"
    assert RiskTier.MEDIUM == "medium"
    assert RiskTier.HIGH == "high"
    assert RiskTier.PROHIBITED == "prohibited"


def test_document_type_enum_values():
    assert DocumentType.CERTIFICATE_OF_INCORPORATION == "certificate_of_incorporation"
    assert DocumentType.UBO_ID_PASSPORT == "ubo_id_passport"


# --- Dataclass immutability ---


def test_business_application_is_frozen():
    app = BusinessApplication(
        "app_001",
        "Test Ltd",
        BusinessType.LTD,
        "12345678",
        "GB",
        KYBStatus.SUBMITTED,
        "2026-01-01T00:00:00Z",
    )
    with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
        app.business_name = "Changed"  # type: ignore[misc]


def test_ubo_is_frozen():
    ubo = UltimateBeneficialOwner(
        "ubo_001",
        "app_001",
        "John Doe",
        "GB",
        "1990-01-01",
        Decimal("30"),
        UBOVerification.PENDING,
    )
    with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
        ubo.full_name = "Changed"  # type: ignore[misc]


def test_kyb_document_is_frozen():
    doc = KYBDocument(
        "doc_001", "app_001", DocumentType.PROOF_OF_ADDRESS, "abc123", "2026-01-01T00:00:00Z"
    )
    with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
        doc.file_hash = "changed"  # type: ignore[misc]


def test_kyb_risk_assessment_is_frozen():
    ra = KYBRiskAssessment("ra_001", "app_001", Decimal("30"), RiskTier.MEDIUM)
    with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
        ra.risk_score = Decimal("50")  # type: ignore[misc]


# --- I-01: Decimal ownership_pct ---


def test_ubo_ownership_pct_is_decimal():
    ubo = UltimateBeneficialOwner(
        "ubo_001",
        "app_001",
        "Jane",
        "GB",
        "1985-06-15",
        Decimal("25.5"),
        UBOVerification.PENDING,
    )
    assert isinstance(ubo.ownership_pct, Decimal)


def test_kyb_risk_score_is_decimal():
    ra = KYBRiskAssessment("ra_001", "app_001", Decimal("42.5"), RiskTier.MEDIUM)
    assert isinstance(ra.risk_score, Decimal)


# --- HITLProposal (mutable) ---


def test_hitl_proposal_is_mutable():
    p = HITLProposal("approve", "app_001", "KYB_OFFICER", "test reason")
    p.reason = "updated reason"
    assert p.reason == "updated reason"


def test_hitl_proposal_default_autonomy():
    p = HITLProposal("approve", "app_001", "KYB_OFFICER", "reason")
    assert p.autonomy_level == "L4"


# --- InMemory stores ---


def test_inmemory_application_store_seeded():
    store = InMemoryApplicationStore()
    assert store.get("app_001") is not None
    assert store.get("app_002") is not None
    assert store.get("app_003") is not None


def test_inmemory_application_store_get_missing():
    store = InMemoryApplicationStore()
    assert store.get("nonexistent") is None


def test_inmemory_application_store_save_and_get():
    store = InMemoryApplicationStore()
    app = BusinessApplication(
        "app_new",
        "New Corp",
        BusinessType.LTD,
        "99999999",
        "GB",
        KYBStatus.SUBMITTED,
        "2026-01-01T00:00:00Z",
    )
    store.save(app)
    assert store.get("app_new") is not None


def test_inmemory_application_store_list_by_status():
    store = InMemoryApplicationStore()
    approved = store.list_by_status(KYBStatus.APPROVED)
    assert any(a.application_id == "app_001" for a in approved)


def test_inmemory_application_store_list_all():
    store = InMemoryApplicationStore()
    all_apps = store.list_by_status(None)
    assert len(all_apps) >= 3


def test_inmemory_ubo_store_save_get():
    store = InMemoryUBOStore()
    ubo = UltimateBeneficialOwner(
        "ubo_x",
        "app_001",
        "Test User",
        "GB",
        "1990-01-01",
        Decimal("30"),
        UBOVerification.PENDING,
    )
    store.save(ubo)
    assert store.get("ubo_x") is not None


def test_inmemory_ubo_store_list_by_application():
    store = InMemoryUBOStore()
    ubo = UltimateBeneficialOwner(
        "ubo_x",
        "app_001",
        "Test",
        "GB",
        "1990-01-01",
        Decimal("30"),
        UBOVerification.PENDING,
    )
    store.save(ubo)
    result = store.list_by_application("app_001")
    assert len(result) >= 1


def test_inmemory_decision_store_append_only():
    store = InMemoryKYBDecisionStore()
    d = KYBDecision(
        "dec_001",
        "app_001",
        KYBStatus.APPROVED,
        "officer",
        "2026-01-01T00:00:00Z",
        "all good",
        RiskTier.LOW,
    )
    store.append(d)
    assert store.get_latest("app_001") is not None


def test_inmemory_decision_store_no_delete_method():
    store = InMemoryKYBDecisionStore()
    assert not hasattr(store, "delete")
    assert not hasattr(store, "update")
