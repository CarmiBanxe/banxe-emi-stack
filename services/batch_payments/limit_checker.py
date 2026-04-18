"""
services/batch_payments/limit_checker.py — Batch payment limit and AML checks
IL-BPP-01 | Phase 36 | banxe-emi-stack
I-01: Decimal amounts. I-04: EDD threshold £10k.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from services.batch_payments.models import (
    AuditPort,
    BatchPort,
    InMemoryAuditStore,
    InMemoryBatchStore,
)

BATCH_LIMIT_GBP = Decimal("500000")  # £500k per batch
DAILY_AGGREGATE_LIMIT_GBP = Decimal("2000000")  # £2M daily
AML_THRESHOLD_GBP = Decimal("10000")  # £10k EDD trigger I-04
_MAX_BATCHES_PER_WINDOW = 10


class LimitChecker:
    """Enforce batch, daily, and AML limits (I-01, I-04)."""

    def __init__(
        self,
        batch_port: BatchPort | None = None,
        audit_port: AuditPort | None = None,
    ) -> None:
        self._batches: BatchPort = batch_port or InMemoryBatchStore()
        self._audit: AuditPort = audit_port or InMemoryAuditStore()
        self._daily_totals: dict[str, Decimal] = {}
        self._batch_timestamps: dict[str, list[datetime]] = {}

    def check_batch_limit(self, total_amount: Decimal) -> bool:
        """True if total_amount <= £500k batch limit."""
        return total_amount <= BATCH_LIMIT_GBP

    def check_daily_limit(self, created_by: str, check_date: date, new_amount: Decimal) -> bool:
        """True if daily aggregate including new_amount <= £2M (I-01 Decimal)."""
        key = f"{created_by}:{check_date.isoformat()}"
        current = self._daily_totals.get(key, Decimal("0"))
        projected = current + new_amount
        if projected <= DAILY_AGGREGATE_LIMIT_GBP:
            self._daily_totals[key] = projected
            return True
        return False

    def check_aml_threshold(self, item_amount: Decimal) -> bool:
        """True if item_amount >= AML_THRESHOLD — triggers EDD (I-04)."""
        return item_amount >= AML_THRESHOLD_GBP

    def check_velocity(self, created_by: str, window_hours: int = 24) -> bool:
        """True if batches submitted in window <= 10."""
        from datetime import timedelta  # noqa: PLC0415

        now = datetime.utcnow()
        cutoff = now - timedelta(hours=window_hours)
        timestamps = self._batch_timestamps.get(created_by, [])
        recent = [t for t in timestamps if t >= cutoff]
        if len(recent) >= _MAX_BATCHES_PER_WINDOW:
            return False
        recent.append(now)
        self._batch_timestamps[created_by] = recent
        return True

    def get_limit_summary(self) -> dict[str, str]:
        return {
            "batch_limit_gbp": str(BATCH_LIMIT_GBP),
            "daily_aggregate_limit_gbp": str(DAILY_AGGREGATE_LIMIT_GBP),
            "aml_threshold_gbp": str(AML_THRESHOLD_GBP),
            "max_batches_per_24h": str(_MAX_BATCHES_PER_WINDOW),
        }
