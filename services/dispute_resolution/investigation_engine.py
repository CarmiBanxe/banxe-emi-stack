"""
services/dispute_resolution/investigation_engine.py — Investigation workflow
IL-DRM-01 | Phase 33 | banxe-emi-stack
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime

from services.dispute_resolution.models import (
    DisputePort,
    DisputeStatus,
    EvidencePort,
    InMemoryDisputeStore,
    InMemoryEvidenceStore,
)

_VALID_LIABLE_PARTIES = {"MERCHANT", "ISSUER", "SHARED"}


class InvestigationEngine:
    def __init__(
        self,
        dispute_store: DisputePort | None = None,
        evidence_store: EvidencePort | None = None,
    ) -> None:
        self._disputes = dispute_store or InMemoryDisputeStore()
        self._evidence = evidence_store or InMemoryEvidenceStore()

    def assign_investigator(self, dispute_id: str, investigator_id: str) -> dict[str, str]:
        dispute = self._disputes.get(dispute_id)
        if dispute is None:
            raise ValueError(f"Dispute {dispute_id} not found")
        updated = dataclasses.replace(
            dispute,
            investigator_id=investigator_id,
            status=DisputeStatus.UNDER_INVESTIGATION,
        )
        self._disputes.update(updated)
        return {
            "dispute_id": dispute_id,
            "investigator_id": investigator_id,
            "status": DisputeStatus.UNDER_INVESTIGATION.value,
        }

    def gather_evidence(self, dispute_id: str) -> dict[str, object]:
        dispute = self._disputes.get(dispute_id)
        if dispute is None:
            raise ValueError(f"Dispute {dispute_id} not found")
        records = self._evidence.list_by_dispute(dispute_id)
        return {
            "dispute_id": dispute_id,
            "evidence_count": len(records),
            "evidence": [
                {
                    "evidence_id": e.evidence_id,
                    "evidence_type": e.evidence_type.value,
                    "file_hash": e.file_hash,
                    "submitted_at": e.submitted_at.isoformat(),
                }
                for e in records
            ],
        }

    def assess_liability(self, dispute_id: str, liable_party: str) -> dict[str, str]:
        if liable_party not in _VALID_LIABLE_PARTIES:
            raise ValueError(
                f"Invalid liable_party: {liable_party}. Must be one of {_VALID_LIABLE_PARTIES}"
            )
        dispute = self._disputes.get(dispute_id)
        if dispute is None:
            raise ValueError(f"Dispute {dispute_id} not found")
        updated = dataclasses.replace(dispute, liability_party=liable_party)
        self._disputes.update(updated)
        return {
            "dispute_id": dispute_id,
            "liable_party": liable_party,
            "assessment_at": datetime.now(UTC).isoformat(),
        }

    def request_additional_evidence(self, dispute_id: str) -> dict[str, str]:
        dispute = self._disputes.get(dispute_id)
        if dispute is None:
            raise ValueError(f"Dispute {dispute_id} not found")
        updated = dataclasses.replace(dispute, status=DisputeStatus.PENDING_EVIDENCE)
        self._disputes.update(updated)
        return {
            "dispute_id": dispute_id,
            "status": DisputeStatus.PENDING_EVIDENCE.value,
        }
