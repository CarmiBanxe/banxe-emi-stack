"""
services/dispute_resolution/escalation_manager.py — SLA monitoring and FOS escalation (DISP 1.6)
IL-DRM-01 | Phase 33 | banxe-emi-stack
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
import uuid

from services.dispute_resolution.models import (
    DisputePort,
    DisputeStatus,
    EscalationLevel,
    EscalationPort,
    EscalationRecord,
    InMemoryDisputeStore,
    InMemoryEscalationStore,
)


class EscalationManager:
    def __init__(
        self,
        dispute_store: DisputePort | None = None,
        escalation_store: EscalationPort | None = None,
    ) -> None:
        self._disputes = dispute_store or InMemoryDisputeStore()
        self._escalations = escalation_store or InMemoryEscalationStore()

    def check_sla_breach(self, dispute_id: str) -> bool:
        """Returns True if the 8-week SLA (DISP 1.3) has been breached."""
        dispute = self._disputes.get(dispute_id)
        if dispute is None:
            raise ValueError(f"Dispute {dispute_id} not found")
        return datetime.now(UTC) > dispute.sla_deadline

    def escalate_dispute(
        self,
        dispute_id: str,
        reason: str,
        level: EscalationLevel = EscalationLevel.LEVEL_1,
    ) -> dict[str, str]:
        dispute = self._disputes.get(dispute_id)
        if dispute is None:
            raise ValueError(f"Dispute {dispute_id} not found")
        record = EscalationRecord(
            escalation_id=str(uuid.uuid4()),
            dispute_id=dispute_id,
            level=level,
            reason=reason,
            escalated_at=datetime.now(UTC),
        )
        self._escalations.save(record)
        updated = dataclasses.replace(dispute, status=DisputeStatus.ESCALATED)
        self._disputes.update(updated)
        return {
            "escalation_id": record.escalation_id,
            "dispute_id": dispute_id,
            "level": level.value,
            "status": DisputeStatus.ESCALATED.value,
        }

    def escalate_to_fos(self, dispute_id: str, reason: str) -> dict[str, str]:
        """DISP 1.6 — Financial Ombudsman Service referral after 8-week SLA breach."""
        return self.escalate_dispute(dispute_id, reason, level=EscalationLevel.FOS)

    def get_escalations(self, dispute_id: str) -> dict[str, object]:
        records = self._escalations.list_by_dispute(dispute_id)
        return {
            "dispute_id": dispute_id,
            "count": len(records),
            "escalations": [
                {
                    "escalation_id": r.escalation_id,
                    "level": r.level.value,
                    "reason": r.reason,
                    "escalated_at": r.escalated_at.isoformat(),
                }
                for r in records
            ],
        }
