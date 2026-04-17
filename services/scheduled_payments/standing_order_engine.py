"""
services/scheduled_payments/standing_order_engine.py — Standing order lifecycle
IL-SOD-01 | Phase 32 | banxe-emi-stack
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import uuid

from services.scheduled_payments.models import (
    InMemoryStandingOrderStore,
    PaymentFrequency,
    ScheduleStatus,
    StandingOrder,
    StandingOrderPort,
)

_FREQUENCY_DAYS: dict[PaymentFrequency, int] = {
    PaymentFrequency.DAILY: 1,
    PaymentFrequency.WEEKLY: 7,
    PaymentFrequency.FORTNIGHTLY: 14,
    PaymentFrequency.MONTHLY: 30,
    PaymentFrequency.QUARTERLY: 91,
    PaymentFrequency.ANNUAL: 365,
}


class StandingOrderEngine:
    def __init__(self, store: StandingOrderPort | None = None) -> None:
        self._store = store or InMemoryStandingOrderStore()

    def create_standing_order(
        self,
        customer_id: str,
        from_account: str,
        to_account: str,
        amount: Decimal,
        frequency: PaymentFrequency,
        start_date: datetime,
        end_date: datetime | None = None,
        reference: str = "",
    ) -> dict[str, object]:
        if amount <= Decimal("0"):
            raise ValueError("Amount must be positive")
        so = StandingOrder(
            so_id=str(uuid.uuid4()),
            customer_id=customer_id,
            from_account=from_account,
            to_account=to_account,
            amount=amount,
            frequency=frequency,
            start_date=start_date,
            end_date=end_date,
            next_execution_date=start_date,
            status=ScheduleStatus.ACTIVE,
            reference=reference,
            created_at=datetime.now(UTC),
        )
        self._store.save(so)
        return {
            "so_id": so.so_id,
            "customer_id": customer_id,
            "amount": str(amount),
            "frequency": frequency.value,
            "status": ScheduleStatus.ACTIVE.value,
            "next_execution_date": start_date.isoformat(),
        }

    def cancel_standing_order(self, so_id: str) -> dict[str, str]:
        so = self._store.get(so_id)
        if so is None:
            raise ValueError(f"Standing order not found: {so_id}")
        if so.status == ScheduleStatus.CANCELLED:
            raise ValueError(f"Standing order {so_id} already cancelled")
        self._store.update(dataclasses.replace(so, status=ScheduleStatus.CANCELLED))
        return {"so_id": so_id, "status": ScheduleStatus.CANCELLED.value}

    def pause_standing_order(self, so_id: str) -> dict[str, str]:
        so = self._store.get(so_id)
        if so is None:
            raise ValueError(f"Standing order not found: {so_id}")
        if so.status != ScheduleStatus.ACTIVE:
            raise ValueError("Only ACTIVE orders can be paused")
        self._store.update(dataclasses.replace(so, status=ScheduleStatus.PAUSED))
        return {"so_id": so_id, "status": ScheduleStatus.PAUSED.value}

    def resume_standing_order(self, so_id: str) -> dict[str, str]:
        so = self._store.get(so_id)
        if so is None:
            raise ValueError(f"Standing order not found: {so_id}")
        if so.status != ScheduleStatus.PAUSED:
            raise ValueError("Only PAUSED orders can be resumed")
        self._store.update(dataclasses.replace(so, status=ScheduleStatus.ACTIVE))
        return {"so_id": so_id, "status": ScheduleStatus.ACTIVE.value}

    def advance_next_execution_date(self, so_id: str) -> dict[str, str]:
        so = self._store.get(so_id)
        if so is None:
            raise ValueError(f"Standing order not found: {so_id}")
        days = _FREQUENCY_DAYS[so.frequency]
        next_date = so.next_execution_date + timedelta(days=days)
        if so.end_date and next_date > so.end_date:
            updated = dataclasses.replace(so, status=ScheduleStatus.COMPLETED)
        else:
            updated = dataclasses.replace(so, next_execution_date=next_date)
        self._store.update(updated)
        return {
            "so_id": so_id,
            "next_execution_date": updated.next_execution_date.isoformat(),
            "status": updated.status.value,
        }

    def list_standing_orders(self, customer_id: str) -> dict[str, object]:
        orders = self._store.list_by_customer(customer_id)
        return {
            "customer_id": customer_id,
            "standing_orders": [
                {
                    "so_id": o.so_id,
                    "amount": str(o.amount),
                    "frequency": o.frequency.value,
                    "status": o.status.value,
                    "next_execution_date": o.next_execution_date.isoformat(),
                }
                for o in orders
            ],
            "count": len(orders),
        }
