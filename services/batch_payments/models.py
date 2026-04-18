"""
services/batch_payments/models.py — Domain models for Batch Payment Processing
IL-BPP-01 | Phase 36 | banxe-emi-stack
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Protocol, runtime_checkable


class BatchStatus(str, Enum):
    DRAFT = "DRAFT"
    VALIDATING = "VALIDATING"
    VALIDATED = "VALIDATED"
    HITL_REQUIRED = "HITL_REQUIRED"
    SUBMITTED = "SUBMITTED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class PaymentRail(str, Enum):
    FPS = "FPS"
    BACS = "BACS"
    CHAPS = "CHAPS"
    SEPA = "SEPA"
    SWIFT = "SWIFT"


class BatchItemStatus(str, Enum):
    PENDING = "PENDING"
    VALIDATED = "VALIDATED"
    DISPATCHED = "DISPATCHED"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"


class FileFormat(str, Enum):
    BACS_STD18 = "BACS_STD18"
    SEPA_PAIN001 = "SEPA_PAIN001"
    CSV_BANXE = "CSV_BANXE"
    SWIFT_MT103 = "SWIFT_MT103"


class ValidationErrorCode(str, Enum):
    INVALID_IBAN = "INVALID_IBAN"
    INVALID_AMOUNT = "INVALID_AMOUNT"
    BLOCKED_JURISDICTION = "BLOCKED_JURISDICTION"
    EXCEEDS_LIMIT = "EXCEEDS_LIMIT"
    DUPLICATE_ITEM = "DUPLICATE_ITEM"
    MISSING_FIELD = "MISSING_FIELD"


@dataclasses.dataclass(frozen=True)
class BatchRecord:
    id: str
    name: str
    status: BatchStatus
    rail: PaymentRail
    file_format: FileFormat
    total_amount: Decimal
    item_count: int
    created_by: str
    created_at: datetime
    file_hash: str
    submitted_at: datetime | None = None


@dataclasses.dataclass(frozen=True)
class BatchItem:
    id: str
    batch_id: str
    ref: str
    beneficiary_iban: str
    beneficiary_name: str
    amount: Decimal
    currency: str
    status: BatchItemStatus
    error_code: ValidationErrorCode | None = None


@dataclasses.dataclass(frozen=True)
class BatchValidationResult:
    batch_id: str
    is_valid: bool
    errors: list[ValidationErrorCode]
    warnings: list[str]
    validated_at: datetime


@dataclasses.dataclass(frozen=True)
class BatchDispatchResult:
    batch_id: str
    dispatched: int
    failed: int
    rail: PaymentRail
    timestamp: datetime


@dataclasses.dataclass(frozen=True)
class BatchReconciliationReport:
    batch_id: str
    total_items: int
    matched: int
    partial: int
    failed: int
    discrepancy_amount: Decimal
    generated_at: datetime


@runtime_checkable
class BatchPort(Protocol):
    def get_batch(self, batch_id: str) -> BatchRecord | None: ...
    def save_batch(self, batch: BatchRecord) -> None: ...
    def list_batches(self, created_by: str) -> list[BatchRecord]: ...


@runtime_checkable
class BatchItemPort(Protocol):
    def get_items(self, batch_id: str) -> list[BatchItem]: ...
    def save_item(self, item: BatchItem) -> None: ...
    def update_status(self, item_id: str, status: BatchItemStatus) -> None: ...


@runtime_checkable
class AuditPort(Protocol):
    def log(self, action: str, resource_id: str, details: str, outcome: str) -> None: ...


@runtime_checkable
class PaymentGatewayPort(Protocol):
    def dispatch(self, item: BatchItem, rail: PaymentRail) -> str: ...


class InMemoryBatchStore:
    def __init__(self) -> None:
        self._data: dict[str, BatchRecord] = {}

    def get_batch(self, batch_id: str) -> BatchRecord | None:
        return self._data.get(batch_id)

    def save_batch(self, batch: BatchRecord) -> None:
        self._data[batch.id] = batch

    def list_batches(self, created_by: str) -> list[BatchRecord]:
        return [b for b in self._data.values() if b.created_by == created_by]


class InMemoryBatchItemStore:
    def __init__(self) -> None:
        self._data: dict[str, BatchItem] = {}
        self._by_batch: dict[str, list[str]] = {}

    def get_items(self, batch_id: str) -> list[BatchItem]:
        ids = self._by_batch.get(batch_id, [])
        return [self._data[i] for i in ids if i in self._data]

    def save_item(self, item: BatchItem) -> None:
        self._data[item.id] = item
        lst = self._by_batch.setdefault(item.batch_id, [])
        if item.id not in lst:
            lst.append(item.id)

    def update_status(self, item_id: str, item_status: BatchItemStatus) -> None:
        item = self._data.get(item_id)
        if item is not None:
            import dataclasses as dc  # noqa: PLC0415

            self._data[item_id] = dc.replace(item, status=item_status)


class InMemoryAuditStore:
    """Append-only audit store (I-24)."""

    def __init__(self) -> None:
        self._records: list[dict[str, str]] = []

    def log(self, action: str, resource_id: str, details: str, outcome: str) -> None:
        self._records.append(
            {"action": action, "resource_id": resource_id, "details": details, "outcome": outcome}
        )

    def get_records(self) -> list[dict[str, str]]:
        return list(self._records)


class InMemoryPaymentGateway:
    """Stub payment gateway."""

    def dispatch(self, item: BatchItem, rail: PaymentRail) -> str:
        return f"conf-{item.id[:8]}-{rail.value}"
