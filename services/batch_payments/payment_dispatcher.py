"""
services/batch_payments/payment_dispatcher.py — Batch payment dispatching
IL-BPP-01 | Phase 36 | banxe-emi-stack
"""

from __future__ import annotations

from datetime import UTC, datetime

from services.batch_payments.models import (
    AuditPort,
    BatchDispatchResult,
    BatchItem,
    BatchItemPort,
    BatchItemStatus,
    BatchPort,
    InMemoryAuditStore,
    InMemoryBatchItemStore,
    InMemoryBatchStore,
    InMemoryPaymentGateway,
    PaymentGatewayPort,
    PaymentRail,
)


class PaymentDispatcher:
    """Dispatches validated batch items to payment gateway."""

    def __init__(
        self,
        batch_port: BatchPort | None = None,
        item_port: BatchItemPort | None = None,
        gateway_port: PaymentGatewayPort | None = None,
        audit_port: AuditPort | None = None,
    ) -> None:
        self._batches: BatchPort = batch_port or InMemoryBatchStore()
        self._items: BatchItemPort = item_port or InMemoryBatchItemStore()
        self._gateway: PaymentGatewayPort = gateway_port or InMemoryPaymentGateway()
        self._audit: AuditPort = audit_port or InMemoryAuditStore()

    def dispatch_batch(self, batch_id: str) -> BatchDispatchResult:
        """Dispatch all VALIDATED items in batch."""
        batch = self._batches.get_batch(batch_id)
        if batch is None:
            raise ValueError(f"Batch not found: {batch_id}")
        items = self._items.get_items(batch_id)
        dispatched = 0
        failed = 0
        for item in items:
            if item.status == BatchItemStatus.VALIDATED:
                try:
                    self.dispatch_item(item, batch.rail)
                    dispatched += 1
                except Exception:  # noqa: BLE001
                    self._items.update_status(item.id, BatchItemStatus.FAILED)
                    failed += 1
        self._audit.log(
            "DISPATCH_BATCH", batch_id, f"dispatched={dispatched} failed={failed}", "OK"
        )
        return BatchDispatchResult(
            batch_id=batch_id,
            dispatched=dispatched,
            failed=failed,
            rail=batch.rail,
            timestamp=datetime.now(UTC),
        )

    def dispatch_item(self, item: BatchItem, rail: PaymentRail) -> BatchItem:
        """Dispatch a single item, update status to DISPATCHED."""
        _ref = self._gateway.dispatch(item, rail)
        self._items.update_status(item.id, BatchItemStatus.DISPATCHED)
        self._audit.log("DISPATCH_ITEM", item.id, f"rail={rail.value} ref={_ref}", "DISPATCHED")
        import dataclasses  # noqa: PLC0415

        return dataclasses.replace(item, status=BatchItemStatus.DISPATCHED)

    def get_dispatch_status(self, batch_id: str) -> dict[str, int]:
        """Return summary of dispatched/failed item counts."""
        items = self._items.get_items(batch_id)
        dispatched = sum(1 for i in items if i.status == BatchItemStatus.DISPATCHED)
        failed = sum(1 for i in items if i.status == BatchItemStatus.FAILED)
        confirmed = sum(1 for i in items if i.status == BatchItemStatus.CONFIRMED)
        return {
            "batch_id": batch_id,
            "total": len(items),
            "dispatched": dispatched,
            "confirmed": confirmed,
            "failed": failed,
        }

    def retry_failed_items(self, batch_id: str) -> int:
        """Retry FAILED items, returns count of retried items."""
        batch = self._batches.get_batch(batch_id)
        if batch is None:
            raise ValueError(f"Batch not found: {batch_id}")
        items = self._items.get_items(batch_id)
        retried = 0
        for item in items:
            if item.status == BatchItemStatus.FAILED:
                try:
                    self._items.update_status(item.id, BatchItemStatus.VALIDATED)
                    self._gateway.dispatch(item, batch.rail)
                    self._items.update_status(item.id, BatchItemStatus.DISPATCHED)
                    retried += 1
                except Exception:  # noqa: BLE001
                    self._items.update_status(item.id, BatchItemStatus.FAILED)
        self._audit.log("RETRY_FAILED", batch_id, f"retried={retried}", "OK")
        return retried
