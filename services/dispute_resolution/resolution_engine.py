"""
services/dispute_resolution/resolution_engine.py — Resolution proposal and execution (HITL I-27)
IL-DRM-01 | Phase 33 | banxe-emi-stack
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from decimal import Decimal
import uuid

from services.dispute_resolution.models import (
    DisputePort,
    DisputeStatus,
    InMemoryDisputeStore,
    InMemoryResolutionStore,
    ResolutionOutcome,
    ResolutionPort,
    ResolutionProposal,
)


class ResolutionEngine:
    def __init__(
        self,
        dispute_store: DisputePort | None = None,
        resolution_store: ResolutionPort | None = None,
    ) -> None:
        self._disputes = dispute_store or InMemoryDisputeStore()
        self._resolutions = resolution_store or InMemoryResolutionStore()

    def propose_resolution(
        self,
        dispute_id: str,
        outcome: ResolutionOutcome,
        refund_amount: Decimal | None = None,
        reason: str = "",
    ) -> dict[str, object]:
        """Resolution always requires HITL approval (I-27, DISP 1.6)."""
        dispute = self._disputes.get(dispute_id)
        if dispute is None:
            raise ValueError(f"Dispute {dispute_id} not found")
        proposal = ResolutionProposal(
            proposal_id=str(uuid.uuid4()),
            dispute_id=dispute_id,
            outcome=outcome,
            refund_amount=refund_amount,
            reason=reason,
            proposed_at=datetime.now(UTC),
        )
        self._resolutions.save(proposal)
        return {
            "status": "HITL_REQUIRED",
            "proposal_id": proposal.proposal_id,
            "dispute_id": dispute_id,
            "outcome": outcome.value,
            "refund_amount": str(refund_amount) if refund_amount else None,
        }

    def approve_resolution(self, proposal_id: str, approved_by: str) -> dict[str, str]:
        proposal = self._resolutions.get(proposal_id)
        if proposal is None:
            raise ValueError(f"Proposal {proposal_id} not found")
        now = datetime.now(UTC)
        approved = dataclasses.replace(proposal, approved_by=approved_by, approved_at=now)
        self._resolutions.update(approved)
        dispute = self._disputes.get(proposal.dispute_id)
        if dispute:
            resolved = dataclasses.replace(
                dispute,
                status=DisputeStatus.RESOLVED,
                outcome=proposal.outcome,
                resolved_at=now,
            )
            self._disputes.update(resolved)
        return {
            "proposal_id": proposal_id,
            "dispute_id": proposal.dispute_id,
            "approved_by": approved_by,
            "status": "APPROVED",
        }

    def execute_refund(self, dispute_id: str, amount: Decimal) -> dict[str, str]:
        if amount <= Decimal("0"):
            raise ValueError("Refund amount must be positive (I-01)")
        return {
            "refund_id": str(uuid.uuid4()),
            "dispute_id": dispute_id,
            "amount": str(amount),
            "status": "REFUND_EXECUTED",
        }

    def close_dispute(self, dispute_id: str) -> dict[str, str]:
        dispute = self._disputes.get(dispute_id)
        if dispute is None:
            raise ValueError(f"Dispute {dispute_id} not found")
        closed = dataclasses.replace(dispute, status=DisputeStatus.CLOSED)
        self._disputes.update(closed)
        return {
            "dispute_id": dispute_id,
            "status": DisputeStatus.CLOSED.value,
        }
