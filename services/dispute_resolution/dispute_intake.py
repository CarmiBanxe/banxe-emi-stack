"""
services/dispute_resolution/dispute_intake.py — Dispute filing and evidence submission
IL-DRM-01 | Phase 33 | banxe-emi-stack
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import uuid

from services.dispute_resolution.models import (
    Dispute,
    DisputeEvidence,
    DisputePort,
    DisputeStatus,
    DisputeType,
    EvidencePort,
    EvidenceType,
    InMemoryDisputeStore,
    InMemoryEvidenceStore,
    compute_evidence_hash,
)

_SLA_DAYS = 56  # DISP 1.3 — 8 weeks


class DisputeIntake:
    def __init__(
        self,
        dispute_store: DisputePort | None = None,
        evidence_store: EvidencePort | None = None,
    ) -> None:
        self._disputes = dispute_store or InMemoryDisputeStore()
        self._evidence = evidence_store or InMemoryEvidenceStore()

    def file_dispute(
        self,
        customer_id: str,
        payment_id: str,
        dispute_type: DisputeType,
        amount: Decimal,
        description: str = "",
    ) -> dict[str, object]:
        if amount <= Decimal("0"):
            raise ValueError("Dispute amount must be positive (I-01)")
        now = datetime.now(UTC)
        dispute = Dispute(
            dispute_id=str(uuid.uuid4()),
            customer_id=customer_id,
            payment_id=payment_id,
            dispute_type=dispute_type,
            amount=amount,
            description=description,
            status=DisputeStatus.OPENED,
            created_at=now,
            sla_deadline=now + timedelta(days=_SLA_DAYS),
        )
        self._disputes.save(dispute)
        return {
            "dispute_id": dispute.dispute_id,
            "customer_id": customer_id,
            "payment_id": payment_id,
            "dispute_type": dispute_type.value,
            "amount": str(amount),
            "status": DisputeStatus.OPENED.value,
            "sla_deadline": dispute.sla_deadline.isoformat(),
        }

    def attach_evidence(
        self,
        dispute_id: str,
        evidence_type: EvidenceType,
        file_content: bytes,
        description: str = "",
    ) -> dict[str, str]:
        dispute = self._disputes.get(dispute_id)
        if dispute is None:
            raise ValueError(f"Dispute {dispute_id} not found")
        file_hash = compute_evidence_hash(file_content)
        evidence = DisputeEvidence(
            evidence_id=str(uuid.uuid4()),
            dispute_id=dispute_id,
            evidence_type=evidence_type,
            file_hash=file_hash,
            description=description,
            submitted_at=datetime.now(UTC),
        )
        self._evidence.save(evidence)
        return {
            "evidence_id": evidence.evidence_id,
            "dispute_id": dispute_id,
            "file_hash": file_hash,
            "evidence_type": evidence_type.value,
        }

    def get_dispute(self, dispute_id: str) -> dict[str, object]:
        dispute = self._disputes.get(dispute_id)
        if dispute is None:
            raise ValueError(f"Dispute {dispute_id} not found")
        return {
            "dispute_id": dispute.dispute_id,
            "customer_id": dispute.customer_id,
            "payment_id": dispute.payment_id,
            "dispute_type": dispute.dispute_type.value,
            "amount": str(dispute.amount),
            "status": dispute.status.value,
            "sla_deadline": dispute.sla_deadline.isoformat(),
        }

    def list_disputes(self, customer_id: str) -> dict[str, object]:
        disputes = self._disputes.list_by_customer(customer_id)
        return {
            "customer_id": customer_id,
            "count": len(disputes),
            "disputes": [
                {
                    "dispute_id": d.dispute_id,
                    "status": d.status.value,
                    "amount": str(d.amount),
                }
                for d in disputes
            ],
        }
