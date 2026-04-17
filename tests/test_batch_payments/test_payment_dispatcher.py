"""
tests/test_batch_payments/test_payment_dispatcher.py — Tests for PaymentDispatcher
IL-BPP-01 | Phase 36 | 16 tests
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.batch_payments.batch_creator import BatchCreator
from services.batch_payments.models import (
    BatchItemStatus,
    FileFormat,
    InMemoryAuditStore,
    InMemoryBatchItemStore,
    InMemoryBatchStore,
    InMemoryPaymentGateway,
    PaymentRail,
)
from services.batch_payments.payment_dispatcher import PaymentDispatcher


@pytest.fixture()
def shared_stores():
    batch_store = InMemoryBatchStore()
    item_store = InMemoryBatchItemStore()
    audit = InMemoryAuditStore()
    return batch_store, item_store, audit


@pytest.fixture()
def dispatcher(shared_stores):
    batch_store, item_store, audit = shared_stores
    return PaymentDispatcher(
        batch_port=batch_store,
        item_port=item_store,
        gateway_port=InMemoryPaymentGateway(),
        audit_port=audit,
    )


@pytest.fixture()
def creator(shared_stores):
    batch_store, item_store, audit = shared_stores
    return BatchCreator(batch_port=batch_store, item_port=item_store, audit_port=audit)


def _make_validated_batch(creator, dispatcher):
    batch = creator.create_batch("Test", PaymentRail.FPS, FileFormat.CSV_BANXE, "user-1")
    item = creator.add_item(
        batch.id, "REF001", "GB29NWBK60161331926819", "Alice", Decimal("100"), "GBP"
    )
    dispatcher._items.update_status(item.id, BatchItemStatus.VALIDATED)
    return batch, item


def test_dispatch_batch_returns_result(dispatcher, creator):
    batch, _ = _make_validated_batch(creator, dispatcher)
    result = dispatcher.dispatch_batch(batch.id)
    assert result.batch_id == batch.id


def test_dispatch_batch_dispatched_count(dispatcher, creator):
    batch, _ = _make_validated_batch(creator, dispatcher)
    result = dispatcher.dispatch_batch(batch.id)
    assert result.dispatched == 1


def test_dispatch_batch_failed_count_zero(dispatcher, creator):
    batch, _ = _make_validated_batch(creator, dispatcher)
    result = dispatcher.dispatch_batch(batch.id)
    assert result.failed == 0


def test_dispatch_batch_not_found_raises(dispatcher):
    with pytest.raises(ValueError):
        dispatcher.dispatch_batch("batch-nonexistent")


def test_dispatch_item_sets_dispatched_status(dispatcher, creator):
    batch, item = _make_validated_batch(creator, dispatcher)
    result = dispatcher.dispatch_item(item, batch.rail)
    assert result.status == BatchItemStatus.DISPATCHED


def test_dispatch_item_rail_matches(dispatcher, creator):
    batch, item = _make_validated_batch(creator, dispatcher)
    result = dispatcher.dispatch_item(item, PaymentRail.FPS)
    assert result.status == BatchItemStatus.DISPATCHED


def test_get_dispatch_status_returns_counts(dispatcher, creator):
    batch, _ = _make_validated_batch(creator, dispatcher)
    dispatcher.dispatch_batch(batch.id)
    status = dispatcher.get_dispatch_status(batch.id)
    assert "dispatched" in status
    assert "total" in status


def test_get_dispatch_status_empty_batch(dispatcher, creator):
    batch = creator.create_batch("Empty", PaymentRail.FPS, FileFormat.CSV_BANXE, "user-1")
    status = dispatcher.get_dispatch_status(batch.id)
    assert status["total"] == 0
    assert status["dispatched"] == 0


def test_retry_failed_items_returns_count(dispatcher, creator):
    batch = creator.create_batch("Retry", PaymentRail.FPS, FileFormat.CSV_BANXE, "user-1")
    item = creator.add_item(
        batch.id, "REF001", "GB29NWBK60161331926819", "Alice", Decimal("100"), "GBP"
    )
    dispatcher._items.update_status(item.id, BatchItemStatus.FAILED)
    count = dispatcher.retry_failed_items(batch.id)
    assert count == 1


def test_retry_failed_no_failed_items_returns_zero(dispatcher, creator):
    batch = creator.create_batch("NoFail", PaymentRail.FPS, FileFormat.CSV_BANXE, "user-1")
    count = dispatcher.retry_failed_items(batch.id)
    assert count == 0


def test_retry_failed_not_found_raises(dispatcher):
    with pytest.raises(ValueError):
        dispatcher.retry_failed_items("batch-nonexistent")


def test_dispatch_batch_pending_items_not_dispatched(dispatcher, creator):
    batch = creator.create_batch("Pending", PaymentRail.FPS, FileFormat.CSV_BANXE, "user-1")
    creator.add_item(batch.id, "REF001", "GB29NWBK60161331926819", "Alice", Decimal("100"), "GBP")
    result = dispatcher.dispatch_batch(batch.id)
    assert result.dispatched == 0


def test_dispatch_batch_rail_in_result(dispatcher, creator):
    batch, _ = _make_validated_batch(creator, dispatcher)
    result = dispatcher.dispatch_batch(batch.id)
    assert result.rail == PaymentRail.FPS


def test_dispatch_batch_timestamp_set(dispatcher, creator):
    batch, _ = _make_validated_batch(creator, dispatcher)
    result = dispatcher.dispatch_batch(batch.id)
    assert result.timestamp is not None


def test_get_dispatch_status_dispatched_after_dispatch(dispatcher, creator):
    batch, _ = _make_validated_batch(creator, dispatcher)
    dispatcher.dispatch_batch(batch.id)
    status = dispatcher.get_dispatch_status(batch.id)
    assert status["dispatched"] >= 1
