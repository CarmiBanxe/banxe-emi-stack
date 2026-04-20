"""Tests for ApplicationManager — Phase 45 (IL-KYB-01)."""

from __future__ import annotations

import pytest

from services.kyb_onboarding.application_manager import BLOCKED_JURISDICTIONS, ApplicationManager
from services.kyb_onboarding.models import (
    BusinessType,
    DocumentType,
    HITLProposal,
    InMemoryApplicationStore,
    InMemoryKYBDecisionStore,
    InMemoryKYBDocumentStore,
    KYBStatus,
)


def make_manager():
    return ApplicationManager(
        InMemoryApplicationStore(),
        InMemoryKYBDocumentStore(),
        InMemoryKYBDecisionStore(),
    )


# --- submit_application ---


def test_submit_application_creates_app():
    mgr = make_manager()
    app = mgr.submit_application("Test Corp", BusinessType.LTD, "12345678", "GB")
    assert app.application_id.startswith("app_")
    assert app.status == KYBStatus.SUBMITTED


def test_submit_application_generates_sha256_id():
    mgr = make_manager()
    app = mgr.submit_application("Test Corp", BusinessType.LTD, "12345678", "GB")
    assert len(app.application_id) == len("app_") + 8


def test_submit_application_blocked_jurisdiction_ru():
    mgr = make_manager()
    with pytest.raises(ValueError, match="I-02"):
        mgr.submit_application("Russian Corp", BusinessType.LTD, "12345678", "RU")


def test_submit_application_blocked_jurisdiction_ir():
    mgr = make_manager()
    with pytest.raises(ValueError, match="I-02"):
        mgr.submit_application("Iran Corp", BusinessType.LTD, "12345678", "IR")


def test_submit_application_blocked_jurisdiction_kp():
    mgr = make_manager()
    with pytest.raises(ValueError, match="I-02"):
        mgr.submit_application("Corp", BusinessType.LTD, "12345678", "KP")


def test_submit_application_all_blocked_jurisdictions():
    mgr = make_manager()
    for jur in BLOCKED_JURISDICTIONS:
        with pytest.raises(ValueError):
            mgr.submit_application("Corp", BusinessType.LTD, "12345678", jur)


def test_submit_application_stores_in_audit():
    store = InMemoryApplicationStore()
    decision_store = InMemoryKYBDecisionStore()
    mgr = ApplicationManager(store, InMemoryKYBDocumentStore(), decision_store)
    mgr.submit_application("Audit Corp", BusinessType.LTD, "12345678", "GB")
    # audit decision appended
    all_decisions = decision_store._log
    assert len(all_decisions) >= 1


# --- validate_documents ---


def test_validate_documents_missing_docs():
    mgr = make_manager()
    app = mgr.submit_application("Test Ltd", BusinessType.LTD, "12345678", "GB")
    valid, missing = mgr.validate_documents(app.application_id, [])
    assert not valid
    assert "certificate_of_incorporation" in missing


def test_validate_documents_all_present_ltd():
    mgr = make_manager()
    app = mgr.submit_application("Test Ltd", BusinessType.LTD, "12345678", "GB")
    docs = [
        {"document_type": "certificate_of_incorporation"},
        {"document_type": "memorandum_articles"},
    ]
    valid, missing = mgr.validate_documents(app.application_id, docs)
    assert valid
    assert missing == []


def test_validate_documents_invalid_ch_number():
    mgr = make_manager()
    app = mgr.submit_application("Test Ltd", BusinessType.LTD, "INVALID", "GB")
    valid, missing = mgr.validate_documents(app.application_id, [])
    assert not valid
    assert "invalid_companies_house_number" in missing


def test_validate_documents_llp_format():
    mgr = make_manager()
    app = mgr.submit_application("Test LLP", BusinessType.LLP, "OC123456", "GB")
    docs = [
        {"document_type": "certificate_of_incorporation"},
        {"document_type": "shareholder_register"},
    ]
    valid, missing = mgr.validate_documents(app.application_id, docs)
    assert valid


def test_validate_documents_sole_trader_no_ch():
    mgr = make_manager()
    app = mgr.submit_application("Solo", BusinessType.SOLE_TRADER, "", "GB")
    docs = [{"document_type": "proof_of_address"}]
    valid, missing = mgr.validate_documents(app.application_id, docs)
    assert valid


def test_validate_documents_nonexistent_app():
    mgr = make_manager()
    valid, missing = mgr.validate_documents("nonexistent", [])
    assert not valid
    assert "application_not_found" in missing


# --- get_application / list_applications ---


def test_get_application_returns_seeded():
    mgr = make_manager()
    app = mgr.get_application("app_001")
    assert app is not None
    assert app.business_name == "Acme Ltd"


def test_get_application_returns_none_for_missing():
    mgr = make_manager()
    assert mgr.get_application("nonexistent") is None


def test_list_applications_no_filter():
    mgr = make_manager()
    apps = mgr.list_applications()
    assert len(apps) >= 3


def test_list_applications_by_status():
    mgr = make_manager()
    approved = mgr.list_applications(KYBStatus.APPROVED)
    assert all(a.status == KYBStatus.APPROVED for a in approved)


# --- update_status ---


def test_update_status_approved_returns_hitl():
    mgr = make_manager()
    result = mgr.update_status("app_002", KYBStatus.APPROVED, "officer", "all good")
    assert isinstance(result, HITLProposal)
    assert result.autonomy_level == "L4"


def test_update_status_rejected_returns_hitl():
    mgr = make_manager()
    result = mgr.update_status("app_002", KYBStatus.REJECTED, "officer", "fraud risk")
    assert isinstance(result, HITLProposal)


def test_update_status_under_review_returns_app():
    mgr = make_manager()
    from services.kyb_onboarding.models import BusinessApplication

    result = mgr.update_status("app_002", KYBStatus.UNDER_REVIEW, "officer", "reviewing")
    assert isinstance(result, BusinessApplication)
    assert result.status == KYBStatus.UNDER_REVIEW


def test_update_status_nonexistent_raises():
    mgr = make_manager()
    with pytest.raises(ValueError):
        mgr.update_status("nonexistent", KYBStatus.APPROVED, "officer", "reason")


# --- request_additional_docs ---


def test_request_additional_docs_sets_pending():
    mgr = make_manager()
    app = mgr.request_additional_docs("app_002", [DocumentType.PROOF_OF_ADDRESS], "officer")
    assert app.status == KYBStatus.DOCUMENTS_PENDING
