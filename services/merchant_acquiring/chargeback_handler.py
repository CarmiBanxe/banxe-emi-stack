"""
services/merchant_acquiring/chargeback_handler.py
IL-MAG-01 | Phase 20

Chargeback lifecycle: received → investigated → represented → resolved.
Evidence collection and dispute management.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
import uuid

from services.merchant_acquiring.models import (
    ChargebackReason,
    DisputeCase,
    DisputeStatus,
    DisputeStorePort,
    MAAuditPort,
)


class ChargebackHandler:
    """Manages chargeback lifecycle from receipt to resolution."""

    def __init__(self, dispute_store: DisputeStorePort, audit: MAAuditPort) -> None:
        self._dispute_store = dispute_store
        self._audit = audit

    async def receive_chargeback(
        self,
        merchant_id: str,
        payment_id: str,
        amount_str: str,
        currency: str,
        reason: str,
        actor: str,
    ) -> DisputeCase:
        """Record an incoming chargeback dispute."""
        try:
            chargeback_reason = ChargebackReason(reason)
        except ValueError as exc:
            valid = [r.value for r in ChargebackReason]
            raise ValueError(
                f"Invalid chargeback reason {reason!r}. Valid values: {valid}"
            ) from exc

        amount = Decimal(amount_str)
        dispute = DisputeCase(
            id=str(uuid.uuid4()),
            merchant_id=merchant_id,
            payment_id=payment_id,
            amount=amount,
            currency=currency,
            reason=chargeback_reason,
            status=DisputeStatus.RECEIVED,
            received_at=datetime.now(UTC),
            resolved_at=None,
            evidence_submitted=False,
        )
        await self._dispute_store.save(dispute)
        await self._audit.log(
            "chargeback.received",
            merchant_id,
            actor,
            {
                "dispute_id": dispute.id,
                "payment_id": payment_id,
                "amount": amount_str,
                "reason": reason,
            },
        )
        return dispute

    async def investigate(self, dispute_id: str, actor: str) -> DisputeCase:
        """Mark a dispute as under investigation."""
        dispute = await self._dispute_store.get(dispute_id)
        if dispute is None:
            raise ValueError(f"Dispute {dispute_id!r} not found")

        updated = replace(dispute, status=DisputeStatus.UNDER_INVESTIGATION)
        await self._dispute_store.save(updated)
        await self._audit.log(
            "chargeback.investigating",
            dispute.merchant_id,
            actor,
            {"dispute_id": dispute_id},
        )
        return updated

    async def submit_evidence(self, dispute_id: str, actor: str) -> DisputeCase:
        """Submit evidence and move dispute to REPRESENTED status."""
        dispute = await self._dispute_store.get(dispute_id)
        if dispute is None:
            raise ValueError(f"Dispute {dispute_id!r} not found")

        updated = replace(
            dispute,
            evidence_submitted=True,
            status=DisputeStatus.REPRESENTED,
        )
        await self._dispute_store.save(updated)
        await self._audit.log(
            "chargeback.evidence_submitted",
            dispute.merchant_id,
            actor,
            {"dispute_id": dispute_id},
        )
        return updated

    async def resolve(self, dispute_id: str, won: bool, actor: str) -> DisputeCase:
        """Resolve a dispute as win or loss."""
        dispute = await self._dispute_store.get(dispute_id)
        if dispute is None:
            raise ValueError(f"Dispute {dispute_id!r} not found")

        status = DisputeStatus.RESOLVED_WIN if won else DisputeStatus.RESOLVED_LOSS
        updated = replace(
            dispute,
            status=status,
            resolved_at=datetime.now(UTC),
        )
        await self._dispute_store.save(updated)
        await self._audit.log(
            "chargeback.resolved",
            dispute.merchant_id,
            actor,
            {"dispute_id": dispute_id, "won": won, "status": status.value},
        )
        return updated

    async def get_dispute(self, dispute_id: str) -> DisputeCase | None:
        """Retrieve a dispute by ID."""
        return await self._dispute_store.get(dispute_id)

    async def list_disputes(self, merchant_id: str) -> list[DisputeCase]:
        """List all disputes for a merchant."""
        return await self._dispute_store.list_by_merchant(merchant_id)
