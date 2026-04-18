"""
tests/test_batch_payments/test_batch_reconciliation.py — Tests for BatchReconciliationEngine
IL-BPP-01 | Phase 36 | 16 tests
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.batch_payments.batch_creator import BatchCreator
from services.batch_payments.models import (
    BatchItemStatus,
    BatchStatus,
    FileFormat,
    InMemoryAuditStore,
    InMemoryBatchItemStore,
    InMemoryBatchStore,
    PaymentRail,
)
from services.batch_payments.reconciliation_engine import BatchReconciliationEngine


@pytest.fixture()
def shared():
    return InMemoryBatchStore(), InMemoryBatchItemStore(), InMemoryAuditStore()


@pytest.fixture()
def engine(shared):
    bs, is_, aud = shared
    return BatchReconciliationEngine(batch_port=bs, item_port=is_, audit_port=aud)


@pytest.fixture()
def creator(shared):
    bs, is_, aud = shared
    return BatchCreator(batch_port=bs, item_port=is_, audit_port=aud)


def _setup_batch(creator, engine, item_statuses):
    batch = creator.create_batch("Recon Test", PaymentRail.FPS, FileFormat.CSV_BANXE, "user-1")
    items = []
    for i, st in enumerate(item_statuses):
        item = creator.add_item(
            batch.id, f"REF{i}", "GB29NWBK60161331926819", "Payee", Decimal("100"), "GBP"
        )
        engine._items.update_status(item.id, st)
        items.append(item)
    return batch, items


def test_reconcile_batch_returns_report(engine, creator):
    batch, _ = _setup_batch(creator, engine, [BatchItemStatus.CONFIRMED])
    report = engine.reconcile_batch(batch.id)
    assert report.batch_id == batch.id


def test_reconcile_batch_matched_count(engine, creator):
    batch, _ = _setup_batch(creator, engine, [BatchItemStatus.CONFIRMED, BatchItemStatus.CONFIRMED])
    report = engine.reconcile_batch(batch.id)
    assert report.matched == 2


def test_reconcile_batch_failed_count(engine, creator):
    batch, _ = _setup_batch(creator, engine, [BatchItemStatus.CONFIRMED, BatchItemStatus.FAILED])
    report = engine.reconcile_batch(batch.id)
    assert report.failed == 1


def test_reconcile_batch_total_items(engine, creator):
    batch, _ = _setup_batch(
        creator,
        engine,
        [BatchItemStatus.CONFIRMED, BatchItemStatus.FAILED, BatchItemStatus.DISPATCHED],
    )
    report = engine.reconcile_batch(batch.id)
    assert report.total_items == 3


def test_reconcile_batch_discrepancy_amount_decimal(engine, creator):
    batch, _ = _setup_batch(creator, engine, [BatchItemStatus.FAILED])
    report = engine.reconcile_batch(batch.id)
    assert type(report.discrepancy_amount) is Decimal


def test_reconcile_batch_no_discrepancy_when_all_confirmed(engine, creator):
    batch, _ = _setup_batch(creator, engine, [BatchItemStatus.CONFIRMED])
    report = engine.reconcile_batch(batch.id)
    assert report.discrepancy_amount == Decimal("0")


def test_reconcile_batch_not_found_raises(engine):
    with pytest.raises(ValueError):
        engine.reconcile_batch("batch-nonexistent")


def test_get_discrepancy_items_failed(engine, creator):
    batch, items = _setup_batch(
        creator, engine, [BatchItemStatus.FAILED, BatchItemStatus.CONFIRMED]
    )
    disc_items = engine.get_discrepancy_items(batch.id)
    assert len(disc_items) == 1


def test_get_discrepancy_items_empty_when_all_confirmed(engine, creator):
    batch, _ = _setup_batch(creator, engine, [BatchItemStatus.CONFIRMED])
    disc_items = engine.get_discrepancy_items(batch.id)
    assert disc_items == []


def test_generate_report_alias_for_reconcile(engine, creator):
    batch, _ = _setup_batch(creator, engine, [BatchItemStatus.CONFIRMED])
    report = engine.generate_report(batch.id)
    assert report.batch_id == batch.id


def test_mark_reconciled_sets_completed(engine, creator):
    batch, _ = _setup_batch(creator, engine, [BatchItemStatus.CONFIRMED])
    engine.mark_reconciled(batch.id)
    updated = engine._batches.get_batch(batch.id)
    assert updated.status == BatchStatus.COMPLETED


def test_mark_reconciled_not_found_raises(engine):
    with pytest.raises(ValueError):
        engine.mark_reconciled("batch-nonexistent")


def test_reconcile_partial_count(engine, creator):
    batch, _ = _setup_batch(
        creator, engine, [BatchItemStatus.DISPATCHED, BatchItemStatus.CONFIRMED]
    )
    report = engine.reconcile_batch(batch.id)
    assert report.partial >= 1


def test_reconcile_batch_logs_audit(engine, creator, shared):
    _, _, audit = shared
    batch, _ = _setup_batch(creator, engine, [BatchItemStatus.CONFIRMED])
    engine.reconcile_batch(batch.id)
    records = audit.get_records()
    assert any(r["action"] == "RECONCILE_BATCH" for r in records)


def test_reconcile_report_timestamp_set(engine, creator):
    batch, _ = _setup_batch(creator, engine, [BatchItemStatus.CONFIRMED])
    report = engine.reconcile_batch(batch.id)
    assert report.generated_at is not None


def test_reconcile_discrepancy_equals_failed_amount(engine, creator):
    batch, _ = _setup_batch(creator, engine, [BatchItemStatus.FAILED, BatchItemStatus.CONFIRMED])
    report = engine.reconcile_batch(batch.id)
    assert report.discrepancy_amount == Decimal("100")
