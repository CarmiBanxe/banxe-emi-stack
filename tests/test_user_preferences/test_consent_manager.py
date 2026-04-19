"""
tests/test_user_preferences/test_consent_manager.py
IL-UPS-01 | Phase 39 | banxe-emi-stack — 16 tests
"""

from __future__ import annotations

import pytest

from services.user_preferences.consent_manager import ConsentManager, HITLProposal
from services.user_preferences.models import (
    ConsentType,
    InMemoryAuditPort,
    InMemoryConsentPort,
)


def _mgr() -> ConsentManager:
    return ConsentManager(InMemoryConsentPort(), InMemoryAuditPort())


class TestGrantConsent:
    def test_grant_returns_record(self) -> None:
        mgr = _mgr()
        rec = mgr.grant_consent("u1", ConsentType.MARKETING, "1.2.3.4", "web")
        assert rec.user_id == "u1"
        assert rec.status == "GRANTED"

    def test_grant_stores_consent_type(self) -> None:
        mgr = _mgr()
        rec = mgr.grant_consent("u1", ConsentType.ANALYTICS, "1.2.3.4", "app")
        assert rec.consent_type == ConsentType.ANALYTICS

    def test_grant_logs_to_audit(self) -> None:
        audit = InMemoryAuditPort()
        mgr = ConsentManager(InMemoryConsentPort(), audit)
        mgr.grant_consent("u1", ConsentType.MARKETING, "1.1.1.1", "web")
        assert len(audit.entries()) == 1
        assert audit.entries()[0]["action"] == "grant_consent"

    def test_grant_records_ip_address(self) -> None:
        mgr = _mgr()
        rec = mgr.grant_consent("u1", ConsentType.THIRD_PARTY, "192.168.1.1", "web")
        assert rec.ip_address == "192.168.1.1"


class TestWithdrawConsent:
    def test_withdraw_returns_hitl_proposal(self) -> None:
        mgr = _mgr()
        result = mgr.withdraw_consent("u1", ConsentType.MARKETING)
        assert isinstance(result, HITLProposal)

    def test_withdraw_hitl_is_l4(self) -> None:
        mgr = _mgr()
        proposal = mgr.withdraw_consent("u1", ConsentType.ANALYTICS)
        assert proposal.autonomy_level == "L4"

    def test_withdraw_essential_raises(self) -> None:
        mgr = _mgr()
        with pytest.raises(ValueError, match="ESSENTIAL consent cannot be withdrawn"):
            mgr.withdraw_consent("u1", ConsentType.ESSENTIAL)

    def test_withdraw_hitl_has_dpo_approver(self) -> None:
        mgr = _mgr()
        proposal = mgr.withdraw_consent("u1", ConsentType.DATA_SHARING)
        assert proposal.requires_approval_from == "DPO"

    def test_withdraw_hitl_includes_consent_type(self) -> None:
        mgr = _mgr()
        proposal = mgr.withdraw_consent("u1", ConsentType.MARKETING)
        assert "MARKETING" in proposal.reason


class TestConfirmWithdrawal:
    def test_confirm_creates_withdrawn_record(self) -> None:
        mgr = _mgr()
        rec = mgr.confirm_withdrawal("u1", ConsentType.MARKETING)
        assert rec.status == "WITHDRAWN"
        assert rec.withdrawn_at is not None

    def test_confirm_logs_to_audit(self) -> None:
        audit = InMemoryAuditPort()
        mgr = ConsentManager(InMemoryConsentPort(), audit)
        mgr.confirm_withdrawal("u1", ConsentType.ANALYTICS)
        assert any(e["action"] == "confirm_withdrawal" for e in audit.entries())


class TestGetConsentStatus:
    def test_not_set_when_no_record(self) -> None:
        mgr = _mgr()
        status = mgr.get_consent_status("new-user", ConsentType.MARKETING)
        assert status == "NOT_SET"

    def test_granted_after_grant(self) -> None:
        mgr = _mgr()
        mgr.grant_consent("u1", ConsentType.MARKETING, "1.2.3.4", "web")
        assert mgr.get_consent_status("u1", ConsentType.MARKETING) == "GRANTED"

    def test_withdrawn_after_confirm(self) -> None:
        mgr = _mgr()
        mgr.confirm_withdrawal("u1", ConsentType.ANALYTICS)
        assert mgr.get_consent_status("u1", ConsentType.ANALYTICS) == "WITHDRAWN"


class TestEssentialConsent:
    def test_essential_active_for_new_user(self) -> None:
        mgr = _mgr()
        assert mgr.is_essential_consent_active("new-user") is True

    def test_list_consents_empty_for_new_user(self) -> None:
        mgr = _mgr()
        assert mgr.list_consents("new-user") == []

    def test_list_consents_returns_all(self) -> None:
        mgr = _mgr()
        mgr.grant_consent("u1", ConsentType.MARKETING, "1.2.3.4", "web")
        mgr.grant_consent("u1", ConsentType.ANALYTICS, "1.2.3.4", "web")
        records = mgr.list_consents("u1")
        assert len(records) == 2
