"""
services/merchant_acquiring/settlement_engine.py
IL-MAG-01 | Phase 20

T+1 settlement: batch processing, net settlement, split payments.
FEE_RATE = Decimal("0.015")  # 1.5% acquiring fee
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
import uuid

from services.merchant_acquiring.models import (
    MAAuditPort,
    PaymentResult,
    PaymentStorePort,
    SettlementBatch,
    SettlementStatus,
    SettlementStorePort,
)

FEE_RATE = Decimal("0.015")


class SettlementEngine:
    """T+1 settlement batch processing engine."""

    def __init__(
        self,
        payment_store: PaymentStorePort,
        settlement_store: SettlementStorePort,
        audit: MAAuditPort,
    ) -> None:
        self._payment_store = payment_store
        self._settlement_store = settlement_store
        self._audit = audit

    async def create_settlement_batch(self, merchant_id: str, actor: str) -> SettlementBatch:
        """Create a settlement batch for all approved payments."""
        payments = await self._payment_store.list_by_merchant(merchant_id)
        approved = [p for p in payments if p.result == PaymentResult.APPROVED]

        gross = sum((p.amount for p in approved), Decimal("0"))
        fees = (gross * FEE_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        net = gross - fees

        batch = SettlementBatch(
            id=str(uuid.uuid4()),
            merchant_id=merchant_id,
            settlement_date=datetime.now(UTC),
            gross_amount=gross,
            fees=fees,
            net_amount=net,
            payment_count=len(approved),
            status=SettlementStatus.PENDING,
            bank_reference=None,
        )
        await self._settlement_store.save(batch)
        await self._audit.log(
            "settlement.batch_created",
            merchant_id,
            actor,
            {
                "batch_id": batch.id,
                "gross_amount": str(gross),
                "fees": str(fees),
                "net_amount": str(net),
                "payment_count": len(approved),
            },
        )
        return batch

    async def process_settlement(self, batch_id: str, actor: str) -> SettlementBatch:
        """Mark settlement batch as completed with a bank reference."""
        batch = await self._settlement_store.get(batch_id)
        if batch is None:
            raise ValueError(f"Settlement batch {batch_id!r} not found")

        bank_reference = f"BNKREF-{uuid.uuid4().hex[:10].upper()}"
        updated = replace(
            batch,
            status=SettlementStatus.COMPLETED,
            bank_reference=bank_reference,
        )
        await self._settlement_store.save(updated)
        await self._audit.log(
            "settlement.completed",
            batch.merchant_id,
            actor,
            {"batch_id": batch_id, "bank_reference": bank_reference},
        )
        return updated

    async def list_settlements(self, merchant_id: str) -> list[SettlementBatch]:
        """List all settlement batches for a merchant."""
        return await self._settlement_store.list_by_merchant(merchant_id)

    async def get_latest_settlement(self, merchant_id: str) -> SettlementBatch | None:
        """Get the most recent settlement batch for a merchant."""
        return await self._settlement_store.get_latest(merchant_id)
