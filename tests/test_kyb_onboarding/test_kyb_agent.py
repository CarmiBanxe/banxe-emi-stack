"""Tests for KYBAgent — Phase 45 (IL-KYB-01)."""

from __future__ import annotations

from decimal import Decimal

from services.kyb_onboarding.kyb_agent import HITLProposal, KYBAgent
from services.kyb_onboarding.models import (
    InMemoryApplicationStore,
    InMemoryKYBDocumentStore,
    InMemoryUBOStore,
    KYBStatus,
    UBOVerification,
    UltimateBeneficialOwner,
)


def make_agent():
    return KYBAgent(
        InMemoryApplicationStore(),
        InMemoryUBOStore(),
        InMemoryKYBDocumentStore(),
    )


# --- process_application (L1 auto-validate) ---


def test_process_application_valid():
    agent = make_agent()
    result = agent.process_application("app_001")
    assert result["status"] == "validated"
    assert result["next_stage"] == "ubo_verify"


def test_process_application_missing_returns_error():
    agent = make_agent()
    result = agent.process_application("nonexistent")
    assert result["status"] == "error"


def test_process_application_increments_processed():
    agent = make_agent()
    agent.process_application("app_001")
    status = agent.get_agent_status()
    assert status["processed_today"] >= 1


# --- process_ubo_screening ---


def test_process_ubo_screening_no_ubos_clear():
    agent = make_agent()
    result = agent.process_ubo_screening("app_001")
    assert isinstance(result, dict)
    assert result["status"] == "clear"


def test_process_ubo_screening_blocked_nationality_hitl():
    app_store = InMemoryApplicationStore()
    ubo_store = InMemoryUBOStore()
    doc_store = InMemoryKYBDocumentStore()
    agent = KYBAgent(app_store, ubo_store, doc_store)
    # Add blocked UBO
    ubo = UltimateBeneficialOwner(
        "ubo_ru",
        "app_001",
        "Ivan",
        "RU",
        "1980-01-01",
        Decimal("30"),
        UBOVerification.PENDING,
    )
    ubo_store.save(ubo)
    result = agent.process_ubo_screening("app_001")
    assert isinstance(result, HITLProposal)
    assert result.autonomy_level == "L4"
    assert result.requires_approval_from == "MLRO"


def test_process_ubo_screening_clear_ubo_no_hitl():
    app_store = InMemoryApplicationStore()
    ubo_store = InMemoryUBOStore()
    doc_store = InMemoryKYBDocumentStore()
    agent = KYBAgent(app_store, ubo_store, doc_store)
    ubo = UltimateBeneficialOwner(
        "ubo_gb",
        "app_001",
        "John",
        "GB",
        "1990-01-01",
        Decimal("30"),
        UBOVerification.PENDING,
    )
    ubo_store.save(ubo)
    result = agent.process_ubo_screening("app_001")
    assert isinstance(result, dict)
    assert result["status"] == "clear"


# --- process_decision (ALWAYS HITL) ---


def test_process_decision_always_hitl():
    agent = make_agent()
    result = agent.process_decision("app_001", KYBStatus.APPROVED, "good")
    assert isinstance(result, HITLProposal)
    assert result.autonomy_level == "L4"


def test_process_decision_rejected_always_hitl():
    agent = make_agent()
    result = agent.process_decision("app_001", KYBStatus.REJECTED, "fraud")
    assert isinstance(result, HITLProposal)


def test_process_decision_hitl_proposal_fields():
    agent = make_agent()
    result = agent.process_decision("app_001", KYBStatus.APPROVED, "all checks passed")
    assert result.application_id == "app_001"
    assert result.requires_approval_from in ("KYB_OFFICER", "MLRO")
    assert result.reason == "all checks passed"


# --- process_suspension (ALWAYS L4 HITL) ---


def test_process_suspension_always_hitl():
    agent = make_agent()
    result = agent.process_suspension("app_001", "suspicious activity")
    assert isinstance(result, HITLProposal)
    assert result.autonomy_level == "L4"
    assert result.requires_approval_from == "MLRO"
    assert result.action == "kyb_suspend"


# --- get_agent_status ---


def test_get_agent_status_fields():
    agent = make_agent()
    status = agent.get_agent_status()
    assert "autonomy_level" in status
    assert "pending_hitl_count" in status
    assert "processed_today" in status


def test_get_agent_status_autonomy_level():
    agent = make_agent()
    status = agent.get_agent_status()
    assert "L1" in status["autonomy_level"] or "L4" in status["autonomy_level"]


def test_pending_hitl_increments_on_decision():
    agent = make_agent()
    agent.process_decision("app_001", KYBStatus.APPROVED, "ok")
    status = agent.get_agent_status()
    assert status["pending_hitl_count"] >= 1
