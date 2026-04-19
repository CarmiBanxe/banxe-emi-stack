"""
tests/test_user_preferences/test_preferences_agent.py
IL-UPS-01 | Phase 39 | banxe-emi-stack — 12 tests
"""

from __future__ import annotations

from services.user_preferences.models import ConsentType, PreferenceCategory
from services.user_preferences.preferences_agent import HITLProposal, PreferencesAgent


def _agent() -> PreferencesAgent:
    return PreferencesAgent()


class TestProcessPreferenceUpdate:
    def test_returns_dict(self) -> None:
        agent = _agent()
        result = agent.process_preference_update("u1", PreferenceCategory.DISPLAY, "theme", "LIGHT")
        assert isinstance(result, dict)

    def test_returns_l1_autonomy(self) -> None:
        agent = _agent()
        result = agent.process_preference_update("u1", PreferenceCategory.DISPLAY, "theme", "DARK")
        assert result["autonomy_level"] == "L1"

    def test_returns_updated_value(self) -> None:
        agent = _agent()
        result = agent.process_preference_update(
            "u1", PreferenceCategory.SECURITY, "mfa_required", "false"
        )
        assert result["value"] == "false"


class TestConsentWithdrawalHITL:
    def test_returns_hitl_proposal(self) -> None:
        agent = _agent()
        result = agent.process_consent_withdrawal("u1", ConsentType.MARKETING)
        assert isinstance(result, HITLProposal)

    def test_l4_autonomy(self) -> None:
        agent = _agent()
        result = agent.process_consent_withdrawal("u1", ConsentType.ANALYTICS)
        assert result.autonomy_level == "L4"

    def test_requires_dpo_approval(self) -> None:
        agent = _agent()
        result = agent.process_consent_withdrawal("u1", ConsentType.MARKETING)
        assert result.requires_approval_from == "DPO"


class TestErasureHITL:
    def test_erasure_returns_hitl(self) -> None:
        agent = _agent()
        result = agent.process_erasure_request("u1")
        assert isinstance(result, HITLProposal)

    def test_erasure_is_l4(self) -> None:
        agent = _agent()
        result = agent.process_erasure_request("u1")
        assert result.autonomy_level == "L4"


class TestExportAuto:
    def test_export_returns_dict(self) -> None:
        agent = _agent()
        result = agent.process_export_request("u1")
        assert isinstance(result, dict)

    def test_export_l1_autonomy(self) -> None:
        agent = _agent()
        result = agent.process_export_request("u1")
        assert result["autonomy_level"] == "L1"

    def test_export_has_hash(self) -> None:
        agent = _agent()
        result = agent.process_export_request("u1")
        assert result["export_hash"] is not None


class TestAgentStatus:
    def test_get_agent_status(self) -> None:
        agent = _agent()
        status = agent.get_agent_status()
        assert status["agent"] == "PreferencesAgent"
        assert "hitl_gates" in status
