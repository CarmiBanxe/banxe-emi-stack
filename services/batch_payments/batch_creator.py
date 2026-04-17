"""
services/batch_payments/batch_creator.py — Batch creation, item management, validation
IL-BPP-01 | Phase 36 | banxe-emi-stack
I-01: Decimal amounts. I-02: Jurisdiction blocking. I-27: Batch submission always HITL.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from decimal import Decimal
import hashlib
import uuid

from services.batch_payments.batch_agent import BatchAgent, HITLProposal
from services.batch_payments.models import (
    AuditPort,
    BatchItem,
    BatchItemPort,
    BatchItemStatus,
    BatchPort,
    BatchRecord,
    BatchStatus,
    BatchValidationResult,
    FileFormat,
    InMemoryAuditStore,
    InMemoryBatchItemStore,
    InMemoryBatchStore,
    PaymentRail,
    ValidationErrorCode,
)

_BLOCKED_JURISDICTIONS = {"RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE", "SY"}
_SEPA_COUNTRIES = {
    "AT",
    "BE",
    "BG",
    "CY",
    "CZ",
    "DE",
    "DK",
    "EE",
    "ES",
    "FI",
    "FR",
    "GR",
    "HR",
    "HU",
    "IE",
    "IT",
    "LT",
    "LU",
    "LV",
    "MT",
    "NL",
    "PL",
    "PT",
    "RO",
    "SE",
    "SI",
    "SK",
    "GB",
    "IS",
    "LI",
    "NO",
    "CH",
}


def _iban_country(iban: str) -> str:
    return iban[:2].upper() if len(iban) >= 2 else ""


def _validate_iban_format(iban: str) -> bool:
    cleaned = iban.replace(" ", "").upper()
    return len(cleaned) >= 15 and cleaned[:2].isalpha() and cleaned[2:4].isdigit()


class BatchCreator:
    """Create and manage payment batches."""

    def __init__(
        self,
        batch_port: BatchPort | None = None,
        item_port: BatchItemPort | None = None,
        audit_port: AuditPort | None = None,
        agent: BatchAgent | None = None,
    ) -> None:
        self._batches: BatchPort = batch_port or InMemoryBatchStore()
        self._items: BatchItemPort = item_port or InMemoryBatchItemStore()
        self._audit: AuditPort = audit_port or InMemoryAuditStore()
        self._agent: BatchAgent = agent or BatchAgent()

    def create_batch(
        self,
        name: str,
        rail: PaymentRail,
        file_format: FileFormat,
        created_by: str,
    ) -> BatchRecord:
        """Create a new batch in DRAFT status."""
        batch_id = f"batch-{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()
        batch = BatchRecord(
            id=batch_id,
            name=name,
            status=BatchStatus.DRAFT,
            rail=rail,
            file_format=file_format,
            total_amount=Decimal("0"),
            item_count=0,
            created_by=created_by,
            created_at=now,
            file_hash=hashlib.sha256(batch_id.encode()).hexdigest(),
        )
        self._batches.save_batch(batch)
        self._audit.log("CREATE_BATCH", batch_id, f"created_by={created_by}", "OK")
        return batch

    def add_item(
        self,
        batch_id: str,
        ref: str,
        beneficiary_iban: str,
        beneficiary_name: str,
        amount: Decimal,
        currency: str,
    ) -> BatchItem:
        """Add a payment item to a batch (I-01: Decimal amounts)."""
        if amount <= Decimal("0"):
            raise ValueError("Amount must be positive (I-01)")
        batch = self._batches.get_batch(batch_id)
        if batch is None:
            raise ValueError(f"Batch not found: {batch_id}")
        item_id = f"item-{uuid.uuid4().hex[:12]}"
        item = BatchItem(
            id=item_id,
            batch_id=batch_id,
            ref=ref,
            beneficiary_iban=beneficiary_iban,
            beneficiary_name=beneficiary_name,
            amount=amount,
            currency=currency,
            status=BatchItemStatus.PENDING,
        )
        self._items.save_item(item)
        updated = dataclasses.replace(
            batch,
            total_amount=batch.total_amount + amount,
            item_count=batch.item_count + 1,
        )
        self._batches.save_batch(updated)
        self._audit.log("ADD_ITEM", batch_id, f"item_id={item_id} amount={amount}", "OK")
        return item

    def validate_all(self, batch_id: str) -> BatchValidationResult:
        """Validate all items: IBAN, amounts, jurisdictions (I-02)."""
        batch = self._batches.get_batch(batch_id)
        if batch is None:
            raise ValueError(f"Batch not found: {batch_id}")
        items = self._items.get_items(batch_id)
        errors: list[ValidationErrorCode] = []
        warnings: list[str] = []
        seen_refs: set[str] = set()
        for item in items:
            if not _validate_iban_format(item.beneficiary_iban):
                errors.append(ValidationErrorCode.INVALID_IBAN)
            if item.amount <= Decimal("0"):
                errors.append(ValidationErrorCode.INVALID_AMOUNT)
            country = _iban_country(item.beneficiary_iban)
            if country in _BLOCKED_JURISDICTIONS:
                errors.append(ValidationErrorCode.BLOCKED_JURISDICTION)
            if item.ref in seen_refs:
                errors.append(ValidationErrorCode.DUPLICATE_ITEM)
            seen_refs.add(item.ref)
            if not item.beneficiary_name:
                errors.append(ValidationErrorCode.MISSING_FIELD)
        is_valid = len(errors) == 0
        new_status = BatchStatus.VALIDATED if is_valid else BatchStatus.FAILED
        self._batches.save_batch(dataclasses.replace(batch, status=new_status))
        return BatchValidationResult(
            batch_id=batch_id,
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            validated_at=datetime.utcnow(),
        )

    def submit_batch(self, batch_id: str) -> HITLProposal:
        """Submit batch — ALWAYS returns HITL (I-27)."""
        batch = self._batches.get_batch(batch_id)
        if batch is None:
            raise ValueError(f"Batch not found: {batch_id}")
        return self._agent.process_submission(batch_id, batch.total_amount)

    def get_batch_summary(self, batch_id: str) -> dict[str, str]:
        """Return batch summary dict."""
        batch = self._batches.get_batch(batch_id)
        if batch is None:
            raise ValueError(f"Batch not found: {batch_id}")
        return {
            "batch_id": batch_id,
            "status": batch.status.value,
            "total_amount": str(batch.total_amount),
            "item_count": str(batch.item_count),
            "rail": batch.rail.value,
        }
