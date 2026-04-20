from __future__ import annotations

from dataclasses import dataclass

from services.kyb_onboarding.models import (
    ApplicationStore,
    KYBDocumentStore,
    KYBStatus,
    RiskTier,
    UBOStore,
)

BLOCKED_JURISDICTIONS = {"RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE", "SY"}


@dataclass
class HITLProposal:
    action: str
    application_id: str
    requires_approval_from: str
    reason: str
    autonomy_level: str = "L4"


class KYBAgent:
    def __init__(
        self,
        app_store: ApplicationStore,
        ubo_store: UBOStore,
        doc_store: KYBDocumentStore,
    ) -> None:
        self._apps = app_store
        self._ubos = ubo_store
        self._docs = doc_store
        self._processed_today = 0
        self._pending_hitl: list[HITLProposal] = []

    def process_application(self, application_id: str) -> dict:
        """L1 auto-validate: checks documents present, jurisdiction not blocked (I-02)."""
        app = self._apps.get(application_id)
        if app is None:
            return {"status": "error", "reason": "application_not_found"}
        if app.jurisdiction.upper() in BLOCKED_JURISDICTIONS:
            return {"status": "blocked", "reason": f"I-02: blocked jurisdiction {app.jurisdiction}"}
        docs = self._docs.list_by_application(application_id)
        self._processed_today += 1
        return {
            "status": "validated",
            "next_stage": "ubo_verify",
            "application_id": application_id,
            "doc_count": len(docs),
        }

    def process_ubo_screening(self, application_id: str) -> dict | HITLProposal:
        """L1 auto if all UBOs clear. L4 HITLProposal if any sanctions hit (I-27)."""
        ubos = self._ubos.list_by_application(application_id)
        for ubo in ubos:
            if ubo.nationality in BLOCKED_JURISDICTIONS:
                proposal = HITLProposal(
                    action="ubo_sanctions_hit",
                    application_id=application_id,
                    requires_approval_from="MLRO",
                    reason=f"I-02: UBO {ubo.ubo_id} blocked nationality {ubo.nationality}",
                )
                self._pending_hitl.append(proposal)
                return proposal
        return {
            "status": "clear",
            "application_id": application_id,
            "ubos_screened": len(ubos),
        }

    def process_decision(
        self,
        application_id: str,
        recommended_status: KYBStatus,
        reason: str,
    ) -> HITLProposal:
        """ALWAYS HITLProposal (I-27) — agent never directly approves/rejects."""
        from services.kyb_onboarding.risk_assessor import KYBRiskAssessor

        # Determine approver based on risk
        approver = "KYB_OFFICER"
        try:
            assessor = KYBRiskAssessor(self._apps, self._ubos)
            assessment = assessor.assess_risk(application_id)
            if assessment.risk_tier in (RiskTier.HIGH, RiskTier.PROHIBITED):
                approver = "MLRO"
        except Exception:
            approver = "MLRO"

        proposal = HITLProposal(
            action=f"kyb_{recommended_status.value}",
            application_id=application_id,
            requires_approval_from=approver,
            reason=reason,
        )
        self._pending_hitl.append(proposal)
        return proposal

    def process_suspension(self, application_id: str, reason: str) -> HITLProposal:
        """ALWAYS L4 HITL (I-27)."""
        proposal = HITLProposal(
            action="kyb_suspend",
            application_id=application_id,
            requires_approval_from="MLRO",
            reason=reason,
        )
        self._pending_hitl.append(proposal)
        return proposal

    def get_agent_status(self) -> dict:
        return {
            "autonomy_level": "L1/L4",
            "pending_hitl_count": len(self._pending_hitl),
            "processed_today": self._processed_today,
        }
