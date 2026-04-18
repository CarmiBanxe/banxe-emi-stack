"""
services/risk_management/risk_agent.py
IL-RMS-01 | Phase 37 | banxe-emi-stack

Risk Agent — orchestrates scoring, threshold changes, mitigation updates.
I-27: Threshold changes and risk acceptance are always HITL-gated.
L1: auto-scoring; L4: threshold changes and ACCEPTED/TRANSFERRED actions.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from services.risk_management.models import (
    MitigationAction,
    RiskCategory,
    RiskThreshold,
)


@dataclass
class HITLProposal:
    action: str
    resource_id: str
    requires_approval_from: str
    reason: str
    autonomy_level: str = "L4"


class RiskAgent:
    """Facade agent for risk management operations."""

    def __init__(self) -> None:
        from services.risk_management.mitigation_tracker import MitigationTracker
        from services.risk_management.risk_scorer import RiskScorer

        self._scorer = RiskScorer()
        self._tracker = MitigationTracker()

    def process_scoring_request(
        self,
        entity_id: str,
        factors: dict,
        category: RiskCategory,
    ) -> dict:
        """Auto-score entity (L1) — returns score summary."""
        decimal_factors = {k: Decimal(str(v)) for k, v in factors.items()}
        score = self._scorer.score_entity(entity_id, decimal_factors, category)
        return {
            "entity_id": entity_id,
            "score": str(score.score),
            "level": score.level.value,
            "category": score.category.value,
            "model": score.model.value,
            "assessed_at": score.assessed_at.isoformat(),
        }

    def process_threshold_change(
        self,
        category: RiskCategory,
        new_threshold: RiskThreshold,
    ) -> HITLProposal:
        """Threshold changes always require human approval (I-27)."""
        return HITLProposal(
            action="set_threshold",
            resource_id=category.value,
            requires_approval_from="Risk Officer",
            reason=(
                f"Threshold change for {category.value}: "
                f"LOW<={new_threshold.low_max}, MEDIUM<={new_threshold.medium_max}, "
                f"HIGH<={new_threshold.high_max}"
            ),
            autonomy_level="L4",
        )

    def process_mitigation_update(
        self,
        plan_id: str,
        action: MitigationAction,
    ) -> dict | HITLProposal:
        """Update mitigation action; HITL if action is ACCEPTED or TRANSFERRED (I-27)."""
        if action in (MitigationAction.ACCEPTED, MitigationAction.TRANSFERRED):
            return HITLProposal(
                action="update_mitigation",
                resource_id=plan_id,
                requires_approval_from="Risk Officer",
                reason=f"Risk {action.value} requires human approval (I-27)",
                autonomy_level="L4",
            )
        plan = self._tracker.update_action(plan_id, action)
        return {
            "plan_id": plan.id,
            "action": plan.action.value,
            "completed_at": plan.completed_at.isoformat() if plan.completed_at else None,
        }

    def get_agent_status(self) -> dict:
        """Return agent operational status."""
        return {
            "agent": "RiskAgent",
            "status": "operational",
            "autonomy_level": "L1/L4",
            "hitl_gates": ["set_threshold", "risk_acceptance", "risk_transfer"],
            "il": "IL-RMS-01",
        }
