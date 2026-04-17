"""
services/dispute_resolution/dispute_agent.py — L2/L4 orchestration facade
IL-DRM-01 | Phase 33 | banxe-emi-stack
"""

from __future__ import annotations

from decimal import Decimal

from services.dispute_resolution.chargeback_bridge import ChargebackBridge
from services.dispute_resolution.dispute_intake import DisputeIntake
from services.dispute_resolution.escalation_manager import EscalationManager
from services.dispute_resolution.investigation_engine import InvestigationEngine
from services.dispute_resolution.models import (
    DisputeType,
    EscalationLevel,
    EvidenceType,
    InMemoryChargebackStore,
    InMemoryDisputeStore,
    InMemoryEscalationStore,
    InMemoryEvidenceStore,
    InMemoryResolutionStore,
    ResolutionOutcome,
)
from services.dispute_resolution.resolution_engine import ResolutionEngine


class DisputeAgent:
    """L2/L4 orchestration — all resolution decisions are HITL_REQUIRED (I-27, DISP 1.6)."""

    def __init__(self) -> None:
        self._dispute_store = InMemoryDisputeStore()
        self._evidence_store = InMemoryEvidenceStore()
        self._escalation_store = InMemoryEscalationStore()
        self._resolution_store = InMemoryResolutionStore()
        self._chargeback_store = InMemoryChargebackStore()
        self._intake = DisputeIntake(
            dispute_store=self._dispute_store,
            evidence_store=self._evidence_store,
        )
        self._investigation = InvestigationEngine(
            dispute_store=self._dispute_store,
            evidence_store=self._evidence_store,
        )
        self._resolution = ResolutionEngine(
            dispute_store=self._dispute_store,
            resolution_store=self._resolution_store,
        )
        self._escalation = EscalationManager(
            dispute_store=self._dispute_store,
            escalation_store=self._escalation_store,
        )
        self._chargeback = ChargebackBridge(store=self._chargeback_store)

    def open_dispute(
        self,
        customer_id: str,
        payment_id: str,
        dispute_type: DisputeType,
        amount: Decimal,
        description: str = "",
    ) -> dict[str, object]:
        return self._intake.file_dispute(customer_id, payment_id, dispute_type, amount, description)

    def submit_evidence(
        self,
        dispute_id: str,
        evidence_type: EvidenceType,
        file_content: bytes,
        description: str = "",
    ) -> dict[str, str]:
        return self._intake.attach_evidence(dispute_id, evidence_type, file_content, description)

    def get_dispute_status(self, dispute_id: str) -> dict[str, object]:
        return self._intake.get_dispute(dispute_id)

    def propose_resolution(
        self,
        dispute_id: str,
        outcome: ResolutionOutcome,
        refund_amount: Decimal | None = None,
        reason: str = "",
    ) -> dict[str, object]:
        """Always HITL_REQUIRED (I-27, DISP 1.6)."""
        return self._resolution.propose_resolution(dispute_id, outcome, refund_amount, reason)

    def escalate(
        self,
        dispute_id: str,
        reason: str,
        level: EscalationLevel = EscalationLevel.LEVEL_1,
    ) -> dict[str, str]:
        return self._escalation.escalate_dispute(dispute_id, reason, level)

    def get_resolution_report(self, customer_id: str) -> dict[str, object]:
        return self._intake.list_disputes(customer_id)
