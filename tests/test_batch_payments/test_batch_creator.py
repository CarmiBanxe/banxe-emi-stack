"""
tests/test_batch_payments/test_batch_creator.py — Tests for BatchCreator
IL-BPP-01 | Phase 36 | 18 tests
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.batch_payments.batch_agent import HITLProposal
from services.batch_payments.batch_creator import BatchCreator
from services.batch_payments.models import (
    BatchStatus,
    FileFormat,
    InMemoryAuditStore,
    InMemoryBatchItemStore,
    InMemoryBatchStore,
    PaymentRail,
    ValidationErrorCode,
)


@pytest.fixture()
def batch_store():
    return InMemoryBatchStore()


@pytest.fixture()
def item_store():
    return InMemoryBatchItemStore()


@pytest.fixture()
def audit():
    return InMemoryAuditStore()


@pytest.fixture()
def creator(batch_store, item_store, audit):
    return BatchCreator(batch_port=batch_store, item_port=item_store, audit_port=audit)


def test_create_batch_returns_draft(creator):
    batch = creator.create_batch("Test Batch", PaymentRail.FPS, FileFormat.CSV_BANXE, "user-1")
    assert batch.status == BatchStatus.DRAFT


def test_create_batch_total_zero(creator):
    batch = creator.create_batch("Test", PaymentRail.BACS, FileFormat.BACS_STD18, "user-1")
    assert batch.total_amount == Decimal("0")


def test_create_batch_item_count_zero(creator):
    batch = creator.create_batch("Test", PaymentRail.SEPA, FileFormat.SEPA_PAIN001, "user-1")
    assert batch.item_count == 0


def test_create_batch_has_file_hash(creator):
    batch = creator.create_batch("Hash Test", PaymentRail.FPS, FileFormat.CSV_BANXE, "user-1")
    assert len(batch.file_hash) == 64


def test_add_item_increases_total(creator):
    batch = creator.create_batch("Batch", PaymentRail.FPS, FileFormat.CSV_BANXE, "user-1")
    creator.add_item(batch.id, "REF001", "GB29NWBK60161331926819", "Alice", Decimal("100"), "GBP")
    summary = creator.get_batch_summary(batch.id)
    assert Decimal(summary["total_amount"]) == Decimal("100")


def test_add_item_increases_item_count(creator):
    batch = creator.create_batch("Batch", PaymentRail.FPS, FileFormat.CSV_BANXE, "user-1")
    creator.add_item(batch.id, "REF001", "GB29NWBK60161331926819", "Bob", Decimal("50"), "GBP")
    summary = creator.get_batch_summary(batch.id)
    assert summary["item_count"] == "1"


def test_add_item_zero_amount_raises(creator):
    batch = creator.create_batch("Batch", PaymentRail.FPS, FileFormat.CSV_BANXE, "user-1")
    with pytest.raises(ValueError):
        creator.add_item(batch.id, "REF001", "GB29NWBK60161331926819", "Alice", Decimal("0"), "GBP")


def test_add_item_negative_amount_raises(creator):
    batch = creator.create_batch("Batch", PaymentRail.FPS, FileFormat.CSV_BANXE, "user-1")
    with pytest.raises(ValueError):
        creator.add_item(
            batch.id, "REF001", "GB29NWBK60161331926819", "Alice", Decimal("-1"), "GBP"
        )


def test_add_item_batch_not_found_raises(creator):
    with pytest.raises(ValueError, match="not found"):
        creator.add_item("batch-nonexistent", "REF001", "iban", "Alice", Decimal("100"), "GBP")


def test_validate_all_valid_batch(creator):
    batch = creator.create_batch("Batch", PaymentRail.FPS, FileFormat.CSV_BANXE, "user-1")
    creator.add_item(batch.id, "REF001", "GB29NWBK60161331926819", "Alice", Decimal("100"), "GBP")
    result = creator.validate_all(batch.id)
    assert result.is_valid is True
    assert len(result.errors) == 0


def test_validate_all_invalid_iban(creator):
    batch = creator.create_batch("Batch", PaymentRail.FPS, FileFormat.CSV_BANXE, "user-1")
    creator.add_item(batch.id, "REF001", "INVALID", "Alice", Decimal("100"), "GBP")
    result = creator.validate_all(batch.id)
    assert ValidationErrorCode.INVALID_IBAN in result.errors


def test_validate_all_blocked_jurisdiction(creator):
    batch = creator.create_batch("Batch", PaymentRail.SWIFT, FileFormat.CSV_BANXE, "user-1")
    creator.add_item(batch.id, "REF001", "RU29NWBK60161331926819", "Blocked", Decimal("100"), "USD")
    result = creator.validate_all(batch.id)
    assert ValidationErrorCode.BLOCKED_JURISDICTION in result.errors


def test_validate_all_duplicate_ref(creator):
    batch = creator.create_batch("Batch", PaymentRail.FPS, FileFormat.CSV_BANXE, "user-1")
    creator.add_item(batch.id, "SAME_REF", "GB29NWBK60161331926819", "Alice", Decimal("100"), "GBP")
    creator.add_item(batch.id, "SAME_REF", "GB29NWBK60161331926820", "Bob", Decimal("200"), "GBP")
    result = creator.validate_all(batch.id)
    assert ValidationErrorCode.DUPLICATE_ITEM in result.errors


def test_submit_batch_always_hitl(creator):
    batch = creator.create_batch("Batch", PaymentRail.FPS, FileFormat.CSV_BANXE, "user-1")
    proposal = creator.submit_batch(batch.id)
    assert isinstance(proposal, HITLProposal)
    assert proposal.autonomy_level == "L4"


def test_submit_batch_not_found_raises(creator):
    with pytest.raises(ValueError):
        creator.submit_batch("batch-nonexistent")


def test_get_batch_summary_fields(creator):
    batch = creator.create_batch("Summary Test", PaymentRail.CHAPS, FileFormat.CSV_BANXE, "user-2")
    summary = creator.get_batch_summary(batch.id)
    assert "batch_id" in summary
    assert "status" in summary
    assert "total_amount" in summary
    assert "item_count" in summary


def test_create_batch_audit_logged(creator, audit):
    creator.create_batch("Audit Test", PaymentRail.FPS, FileFormat.CSV_BANXE, "user-audit")
    records = audit.get_records()
    assert any(r["action"] == "CREATE_BATCH" for r in records)


def test_add_item_amount_is_decimal(creator):
    batch = creator.create_batch("Batch", PaymentRail.FPS, FileFormat.CSV_BANXE, "user-1")
    item = creator.add_item(
        batch.id, "REF001", "GB29NWBK60161331926819", "Alice", Decimal("100"), "GBP"
    )
    assert type(item.amount) is Decimal
