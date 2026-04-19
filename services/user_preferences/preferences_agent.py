"""
services/user_preferences/preferences_agent.py
IL-UPS-01 | Phase 39 | banxe-emi-stack

PreferencesAgent — orchestrates preference/consent/export operations.
L1: auto preference updates and exports.
L4: consent withdrawal and data erasure (I-27 — irreversible GDPR actions).
"""

from __future__ import annotations

from dataclasses import dataclass

from services.user_preferences.consent_manager import ConsentManager
from services.user_preferences.data_export import DataExport
from services.user_preferences.models import ConsentType, PreferenceCategory
from services.user_preferences.preference_store import PreferenceStore


@dataclass
class HITLProposal:
    action: str
    resource_id: str
    requires_approval_from: str
    reason: str
    autonomy_level: str = "L4"


class PreferencesAgent:
    """Facade agent for user preferences operations."""

    def __init__(self) -> None:
        self._store = PreferenceStore()
        self._consent = ConsentManager()
        self._export = DataExport()

    def process_preference_update(
        self,
        user_id: str,
        category: PreferenceCategory,
        key: str,
        value: str,
    ) -> dict:
        """Auto-apply preference update (L1); return updated preference summary."""
        pref = self._store.set_preference(user_id, category, key, value)
        return {
            "user_id": user_id,
            "category": category.value,
            "key": key,
            "value": value,
            "updated_at": pref.updated_at.isoformat(),
            "autonomy_level": "L1",
        }

    def process_consent_withdrawal(
        self,
        user_id: str,
        consent_type: ConsentType,
    ) -> HITLProposal:
        """Consent withdrawal is always HITL — irreversible GDPR action (I-27)."""
        proposal = self._consent.withdraw_consent(user_id, consent_type)
        return HITLProposal(
            action=proposal.action,
            resource_id=proposal.resource_id,
            requires_approval_from=proposal.requires_approval_from,
            reason=proposal.reason,
            autonomy_level="L4",
        )

    def process_erasure_request(self, user_id: str) -> HITLProposal:
        """GDPR Art.17 erasure is always HITL (I-27)."""
        proposal = self._export.request_erasure(user_id)
        return HITLProposal(
            action=proposal.action,
            resource_id=proposal.resource_id,
            requires_approval_from=proposal.requires_approval_from,
            reason=proposal.reason,
            autonomy_level="L4",
        )

    def process_export_request(self, user_id: str) -> dict:
        """Auto-generate export (L1); return export summary."""
        request = self._export.request_export(user_id)
        completed = self._export.complete_export(request.id, user_id)
        return {
            "request_id": completed.id,
            "user_id": user_id,
            "status": completed.status,
            "export_hash": completed.export_hash,
            "completed_at": completed.completed_at.isoformat() if completed.completed_at else None,
            "autonomy_level": "L1",
        }

    def get_agent_status(self) -> dict:
        """Return agent operational status."""
        return {
            "agent": "PreferencesAgent",
            "status": "operational",
            "autonomy_level": "L1/L4",
            "hitl_gates": ["consent_withdrawal", "data_erasure"],
            "il": "IL-UPS-01",
        }
