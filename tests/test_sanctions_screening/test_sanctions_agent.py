"""Tests for SanctionsAgent — Phase 46 (IL-SRS-01)."""

from __future__ import annotations

from services.sanctions_screening.alert_handler import AlertHandler
from services.sanctions_screening.models import (
    InMemoryAlertStore,
    InMemoryHitStore,
    InMemoryListStore,
    InMemoryScreeningStore,
)
from services.sanctions_screening.sanctions_agent import HITLProposal, SanctionsAgent
from services.sanctions_screening.screening_engine import ScreeningEngine


def make_agent():
    store = InMemoryScreeningStore()
    list_store = InMemoryListStore()
    hit_store = InMemoryHitStore()
    engine = ScreeningEngine(store, list_store, hit_store)
    alert_handler = AlertHandler(InMemoryAlertStore(), hit_store)
    return SanctionsAgent(engine, alert_handler)


# --- process_screening (L1 auto / L4 HITL) ---


def test_process_screening_clear_returns_dict():
    agent = make_agent()
    result = agent.process_screening("John Unknown Person", "individual", "GB")
    assert isinstance(result, dict)
    assert result["status"] == "clear"
    assert result["action"] == "none_required"


def test_process_screening_blocked_nationality_hitl():
    agent = make_agent()
    result = agent.process_screening("Ivan Test", "individual", "RU")
    assert isinstance(result, HITLProposal)
    assert result.autonomy_level == "L4"
    assert result.requires_approval_from == "MLRO"


def test_process_screening_confirmed_requires_mlro():
    agent = make_agent()
    result = agent.process_screening("Ivan Test", "individual", "RU")
    assert isinstance(result, HITLProposal)
    assert result.requires_approval_from == "MLRO"


def test_process_screening_clear_has_request_id():
    agent = make_agent()
    result = agent.process_screening("John Unknown", "individual", "GB")
    assert isinstance(result, dict)
    assert "request_id" in result


# --- process_match_review (I-27 ALWAYS L4) ---


def test_process_match_review_always_hitl():
    agent = make_agent()
    result = agent.process_match_review("alert_001")
    assert isinstance(result, HITLProposal)
    assert result.autonomy_level == "L4"


def test_process_match_review_compliance_officer():
    agent = make_agent()
    result = agent.process_match_review("alert_001")
    assert result.requires_approval_from == "COMPLIANCE_OFFICER"


# --- process_sar_filing (I-27 ALWAYS HITL) ---


def test_process_sar_filing_always_hitl():
    agent = make_agent()
    result = agent.process_sar_filing("req_001", "mlro_ref_001")
    assert isinstance(result, HITLProposal)


def test_process_sar_filing_requires_mlro():
    agent = make_agent()
    result = agent.process_sar_filing("req_001", "mlro_ref_001")
    assert result.requires_approval_from == "MLRO"


def test_process_sar_filing_poca_2002_reason():
    agent = make_agent()
    result = agent.process_sar_filing("req_001", "mlro_ref_001")
    assert "POCA 2002" in result.reason or "SAR" in result.reason


def test_process_sar_filing_increments_counter():
    agent = make_agent()
    agent.process_sar_filing("req_001", "mlro_ref_001")
    status = agent.get_agent_status()
    assert status["sars_pending"] >= 1


# --- process_account_freeze (I-27) ---


def test_process_account_freeze_hitl():
    agent = make_agent()
    result = agent.process_account_freeze("Ivan Petrov", "confirmed sanctions match")
    assert isinstance(result, HITLProposal)
    assert result.requires_approval_from == "MLRO"
    assert result.action == "account_freeze"


def test_process_account_freeze_irreversible_reason():
    agent = make_agent()
    result = agent.process_account_freeze("Ivan Petrov", "reason")
    assert "freeze" in result.reason.lower() or "irreversible" in result.reason.lower()


# --- get_agent_status ---


def test_get_agent_status_fields():
    agent = make_agent()
    status = agent.get_agent_status()
    assert "autonomy_level" in status
    assert "pending_reviews" in status
    assert "sars_pending" in status


def test_get_agent_status_pending_reviews_increments():
    agent = make_agent()
    agent.process_screening("Ivan Test", "individual", "RU")
    status = agent.get_agent_status()
    assert status["pending_reviews"] >= 1
