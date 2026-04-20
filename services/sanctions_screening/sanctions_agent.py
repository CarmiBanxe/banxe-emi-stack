from __future__ import annotations

from dataclasses import dataclass

from services.sanctions_screening.alert_handler import AlertHandler
from services.sanctions_screening.models import (
    ScreeningResult,
)
from services.sanctions_screening.screening_engine import ScreeningEngine


@dataclass
class HITLProposal:
    action: str
    entity_name: str
    requires_approval_from: str
    reason: str
    autonomy_level: str = "L4"


class SanctionsAgent:
    def __init__(
        self,
        screening_engine: ScreeningEngine,
        alert_handler: AlertHandler,
    ) -> None:
        self._engine = screening_engine
        self._alerts = alert_handler
        self._pending_reviews: list[HITLProposal] = []
        self._sars_pending: int = 0

    def process_screening(
        self,
        entity_name: str,
        entity_type: str,
        nationality: str,
        dob: str | None = None,
    ) -> dict | HITLProposal:
        """L1 auto if CLEAR. L4 HITL if POSSIBLE/CONFIRMED (I-27)."""
        report = self._engine.screen_entity(entity_name, entity_type, nationality, dob)
        if report.result == ScreeningResult.CLEAR:
            return {"status": "clear", "action": "none_required", "request_id": report.request_id}
        if report.result == ScreeningResult.POSSIBLE_MATCH:
            proposal = HITLProposal(
                action="review_possible_match",
                entity_name=entity_name,
                requires_approval_from="COMPLIANCE_OFFICER",
                reason=f"Possible match for {entity_name} — manual review required",
            )
            self._pending_reviews.append(proposal)
            return proposal
        # CONFIRMED_MATCH
        proposal = HITLProposal(
            action="review_confirmed_match",
            entity_name=entity_name,
            requires_approval_from="MLRO",
            reason=f"Confirmed match for {entity_name} — MLRO review required (I-02)",
        )
        self._pending_reviews.append(proposal)
        return proposal

    def process_match_review(self, alert_id: str) -> HITLProposal:
        """I-27: L4 ALWAYS."""
        return HITLProposal(
            action="match_review",
            entity_name=f"alert:{alert_id}",
            requires_approval_from="COMPLIANCE_OFFICER",
            reason=f"Manual review required for alert {alert_id}",
        )

    def process_sar_filing(
        self,
        request_id: str,
        mlro_ref: str,
    ) -> HITLProposal:
        """I-27: ALWAYS HITL — POCA 2002 s.330."""
        self._sars_pending += 1
        return HITLProposal(
            action="sar_filing",
            entity_name=request_id,
            requires_approval_from="MLRO",
            reason=f"POCA 2002 s.330 SAR Filing — mlro_ref:{mlro_ref}",
        )

    def process_account_freeze(
        self,
        entity_name: str,
        reason: str,
    ) -> HITLProposal:
        """I-27: freeze is irreversible."""
        return HITLProposal(
            action="account_freeze",
            entity_name=entity_name,
            requires_approval_from="MLRO",
            reason=f"Account freeze (irreversible): {reason}",
        )

    def get_agent_status(self) -> dict:
        return {
            "autonomy_level": "L1/L4",
            "pending_reviews": len(self._pending_reviews),
            "sars_pending": self._sars_pending,
        }
