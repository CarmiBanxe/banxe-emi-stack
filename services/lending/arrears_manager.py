"""
services/lending/arrears_manager.py — Loan arrears monitoring and staging
IL-LCE-01 | Phase 25 | banxe-emi-stack

Tracks arrears records and classifies them into IFRS 9 staging buckets.
All outstanding amounts use Decimal (I-01).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import uuid

from services.lending.models import (
    ArrearsRecord,
    ArrearsStorePort,
    ArrearStage,
    InMemoryArrearsStore,
)


class ArrearsManager:
    """Records and classifies loan arrears using IFRS 9 staging buckets."""

    def __init__(self, store: ArrearsStorePort | None = None) -> None:
        self._store = store or InMemoryArrearsStore()

    def check_arrears(
        self,
        application_id: str,
        customer_id: str,
        days_overdue: int,
        outstanding_amount: Decimal,
    ) -> ArrearsRecord:
        """Create and store an arrears record for an application.

        Args:
            application_id: Loan application in arrears.
            customer_id: Customer associated with the application.
            days_overdue: Number of days the payment is overdue.
            outstanding_amount: Outstanding overdue balance (Decimal).

        Returns:
            New ArrearsRecord with the appropriate stage classification.
        """
        stage = self.get_stage(days_overdue)
        record = ArrearsRecord(
            record_id=str(uuid.uuid4()),
            application_id=application_id,
            customer_id=customer_id,
            stage=stage,
            days_overdue=days_overdue,
            outstanding_amount=outstanding_amount,
            recorded_at=datetime.now(UTC),
        )
        self._store.save(record)
        return record

    def get_arrears_history(self, application_id: str) -> list[ArrearsRecord]:
        """Retrieve all arrears records for an application.

        Args:
            application_id: Loan application ID.

        Returns:
            List of ArrearsRecord sorted chronologically.
        """
        return self._store.list_by_application(application_id)

    @staticmethod
    def get_stage(days_overdue: int) -> ArrearStage:
        """Classify days overdue into IFRS 9 arrear stage.

        Args:
            days_overdue: Number of days payment is overdue (0 = current).

        Returns:
            ArrearStage enum value.
        """
        if days_overdue == 0:
            return ArrearStage.CURRENT
        if days_overdue <= 30:
            return ArrearStage.DAYS_1_30
        if days_overdue <= 60:
            return ArrearStage.DAYS_31_60
        if days_overdue <= 90:
            return ArrearStage.DAYS_61_90
        return ArrearStage.DEFAULT_90_PLUS
