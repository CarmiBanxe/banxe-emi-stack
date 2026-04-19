"""
services/batch_payments/reconciliation_engine.py — Batch payment reconciliation
IL-BPP-01 | Phase 36 | banxe-emi-stack
I-01: Decimal amounts. I-24: Append-only audit.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime

from services.batch_payments.models import (
    AuditPort,
    BatchItemPort,
    BatchItemStatus,
    BatchPort,
    BatchReconciliationReport,
    BatchStatus,
    InMemoryAuditStore,
    InMemoryBatchItemStore,
    InMemoryBatchStore,
)


class BatchReconciliationEngine:
    """Reconcile batch items against gateway confirmations."""

    def __init__(
        self,
        batch_port: BatchPort | None = None,
        item_port: BatchItemPort | None = None,
        audit_port: AuditPort | None = None,
    ) -> None:
        self._batches: BatchPort = batch_port or InMemoryBatchStore()
        self._items: BatchItemPort = item_port or InMemoryBatchItemStore()
        self._audit: AuditPort = audit_port or InMemoryAuditStore()

    def reconcile_batch(self, batch_id: str) -> BatchReconciliationReport:
        """Reconcile dispatched items vs confirmed."""
        batch = self._batches.get_batch(batch_id)
        if batch is None:
            raise ValueError(f"Batch not found: {batch_id}")
        items = self._items.get_items(batch_id)
        matched = sum(1 for i in items if i.status == BatchItemStatus.CONFIRMED)
        failed = sum(1 for i in items if i.status == BatchItemStatus.FAILED)
        partial = sum(1 for i in items if i.status == BatchItemStatus.DISPATCHED)
        failed_amount = sum(i.amount for i in items if i.status == BatchItemStatus.FAILED)
        discrepancy = failed_amount
        report = BatchReconciliationReport(
            batch_id=batch_id,
            total_items=len(items),
            matched=matched,
            partial=partial,
            failed=failed,
            discrepancy_amount=discrepancy,
            generated_at=datetime.now(UTC),
        )
        self._audit.log("RECONCILE_BATCH", batch_id, f"matched={matched} failed={failed}", "OK")
        return report

    def get_discrepancy_items(self, batch_id: str) -> list[object]:
        """Return items with FAILED or unexpected status."""
        items = self._items.get_items(batch_id)
        return [i for i in items if i.status in (BatchItemStatus.FAILED, BatchItemStatus.REJECTED)]

    def generate_report(self, batch_id: str) -> BatchReconciliationReport:
        """Alias for reconcile_batch — generates fresh report."""
        return self.reconcile_batch(batch_id)

    def mark_reconciled(self, batch_id: str) -> None:
        """Mark batch as COMPLETED after reconciliation."""
        batch = self._batches.get_batch(batch_id)
        if batch is None:
            raise ValueError(f"Batch not found: {batch_id}")
        self._batches.save_batch(dataclasses.replace(batch, status=BatchStatus.COMPLETED))
        self._audit.log("MARK_RECONCILED", batch_id, "batch completed", "OK")
