"""
services/scheduled_payments/failure_handler.py — Payment failure management, R-transaction codes
IL-SOD-01 | Phase 32 | banxe-emi-stack
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import uuid

from services.scheduled_payments.models import (
    FailureCode,
    FailureRecord,
    FailureRecordPort,
    InMemoryFailureRecordStore,
    PaymentType,
)

_MAX_RETRIES = 2
_RETRY_DELAYS_DAYS = [1, 3]  # T+1, T+3


class FailureHandler:
    def __init__(self, store: FailureRecordPort | None = None) -> None:
        self._store = store or InMemoryFailureRecordStore()

    def record_failure(
        self,
        payment_id: str,
        payment_type: PaymentType,
        failure_code: FailureCode,
        failure_reason: str,
        customer_id: str = "",
    ) -> dict[str, object]:
        now = datetime.now(UTC)
        existing = self._store.list_by_payment(payment_id)
        previous_failures = len(existing)
        retry_count = previous_failures + 1
        next_retry = None
        if previous_failures < _MAX_RETRIES:
            delay = _RETRY_DELAYS_DAYS[previous_failures]
            next_retry = now + timedelta(days=delay)
        record = FailureRecord(
            failure_id=str(uuid.uuid4()),
            payment_id=payment_id,
            payment_type=payment_type,
            failure_code=failure_code,
            failure_reason=failure_reason,
            failed_at=now,
            customer_id=customer_id,
            retry_count=retry_count,
            next_retry_at=next_retry,
        )
        self._store.save(record)
        return {
            "failure_id": record.failure_id,
            "payment_id": payment_id,
            "failure_code": failure_code.value,
            "retry_count": retry_count,
            "next_retry_at": next_retry.isoformat() if next_retry else None,
            "max_retries_reached": previous_failures >= _MAX_RETRIES,
        }

    def get_failure_summary(self, payment_id: str) -> dict[str, object]:
        records = self._store.list_by_payment(payment_id)
        latest = records[-1] if records else None
        return {
            "payment_id": payment_id,
            "total_failures": len(records),
            "max_retries_reached": len(records) > _MAX_RETRIES,
            "last_failure_code": latest.failure_code.value if latest else None,
            "last_failure_at": latest.failed_at.isoformat() if latest else None,
        }

    def get_customer_failures(self, customer_id: str) -> dict[str, object]:
        records = self._store.list_by_customer(customer_id)
        return {
            "customer_id": customer_id,
            "failures": [
                {
                    "failure_id": r.failure_id,
                    "payment_id": r.payment_id,
                    "failure_code": r.failure_code.value,
                    "failed_at": r.failed_at.isoformat(),
                    "retry_count": r.retry_count,
                }
                for r in records
            ],
            "count": len(records),
        }
