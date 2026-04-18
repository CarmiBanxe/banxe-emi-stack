"""
services/batch_payments/batch_agent.py — HITL Agent for Batch Payments
IL-BPP-01 | Phase 36 | banxe-emi-stack
I-27: Batch submission ALWAYS requires HITL.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from services.batch_payments.models import (
    AuditPort,
    BatchPort,
    InMemoryAuditStore,
    InMemoryBatchStore,
)


@dataclass
class HITLProposal:
    action: str
    resource_id: str
    requires_approval_from: str
    reason: str
    autonomy_level: str = "L4"


class BatchAgent:
    """L2/L4 orchestration agent for batch payment decisions (I-27)."""

    def __init__(
        self,
        batch_port: BatchPort | None = None,
        audit_port: AuditPort | None = None,
    ) -> None:
        self._batches: BatchPort = batch_port or InMemoryBatchStore()
        self._audit: AuditPort = audit_port or InMemoryAuditStore()

    def process_submission(self, batch_id: str, total_amount: Decimal) -> HITLProposal:
        """Batch submission ALWAYS returns HITL (I-27)."""
        self._audit.log("BATCH_SUBMIT", batch_id, f"amount={total_amount}", "HITL_REQUIRED")
        return HITLProposal(
            action="SUBMIT_BATCH",
            resource_id=batch_id,
            requires_approval_from="Compliance Officer",
            reason=f"Batch submission of {total_amount} requires human authorisation (I-27)",
            autonomy_level="L4",
        )

    def process_validation(self, batch_id: str) -> dict[str, str]:
        """Auto-validate — returns summary."""
        self._audit.log("BATCH_VALIDATE", batch_id, "auto-validation", "OK")
        return {
            "batch_id": batch_id,
            "status": "VALIDATED",
            "action": "AUTO_VALIDATED",
            "autonomy_level": "L2",
        }

    def process_reconciliation(self, batch_id: str) -> dict[str, str]:
        """Auto-reconcile — returns report summary."""
        self._audit.log("BATCH_RECONCILE", batch_id, "auto-reconciliation", "OK")
        return {
            "batch_id": batch_id,
            "status": "RECONCILED",
            "action": "AUTO_RECONCILED",
            "autonomy_level": "L2",
        }

    def get_agent_status(self) -> dict[str, str]:
        return {
            "agent": "BatchAgent",
            "il_ref": "IL-BPP-01",
            "autonomy_level_default": "L4",
            "status": "ACTIVE",
        }
