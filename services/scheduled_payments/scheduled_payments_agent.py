"""
services/scheduled_payments/scheduled_payments_agent.py — L2 orchestration facade (IL-SOD-01)
IL-SOD-01 | Phase 32 | banxe-emi-stack
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from services.scheduled_payments.direct_debit_engine import DirectDebitEngine
from services.scheduled_payments.failure_handler import FailureHandler
from services.scheduled_payments.models import (
    DDMandatePort,
    FailureCode,
    FailureRecordPort,
    InMemoryDDMandateStore,
    InMemoryFailureRecordStore,
    InMemoryPaymentScheduleStore,
    InMemoryStandingOrderStore,
    PaymentFrequency,
    PaymentSchedulePort,
    PaymentType,
    StandingOrderPort,
)
from services.scheduled_payments.notification_bridge import NotificationBridge
from services.scheduled_payments.schedule_executor import ScheduleExecutor
from services.scheduled_payments.standing_order_engine import StandingOrderEngine


class ScheduledPaymentsAgent:
    def __init__(
        self,
        so_store: StandingOrderPort | None = None,
        mandate_store: DDMandatePort | None = None,
        schedule_store: PaymentSchedulePort | None = None,
        failure_store: FailureRecordPort | None = None,
    ) -> None:
        self._so_store = so_store or InMemoryStandingOrderStore()
        self._mandate_store = mandate_store or InMemoryDDMandateStore()
        self._schedule_store = schedule_store or InMemoryPaymentScheduleStore()
        self._failure_store = failure_store or InMemoryFailureRecordStore()
        self._so_engine = StandingOrderEngine(store=self._so_store)
        self._dd_engine = DirectDebitEngine(mandate_store=self._mandate_store)
        self._executor = ScheduleExecutor(
            so_store=self._so_store, schedule_store=self._schedule_store
        )
        self._failure_handler = FailureHandler(store=self._failure_store)
        self._notifier = NotificationBridge()

    def create_standing_order(
        self,
        customer_id: str,
        from_account: str,
        to_account: str,
        amount: Decimal,
        frequency: PaymentFrequency | str,
        start_date: datetime,
        end_date: datetime | None = None,
        reference: str = "",
    ) -> dict[str, object]:
        freq = frequency if isinstance(frequency, PaymentFrequency) else PaymentFrequency(frequency)
        return self._so_engine.create_standing_order(
            customer_id=customer_id,
            from_account=from_account,
            to_account=to_account,
            amount=amount,
            frequency=freq,
            start_date=start_date,
            end_date=end_date,
            reference=reference,
        )

    def create_dd_mandate(
        self,
        customer_id: str,
        creditor_id: str,
        creditor_name: str,
        scheme_ref: str,
        service_user_number: str,
    ) -> dict[str, str]:
        return self._dd_engine.create_mandate(
            customer_id=customer_id,
            creditor_id=creditor_id,
            creditor_name=creditor_name,
            scheme_ref=scheme_ref,
            service_user_number=service_user_number,
        )

    def cancel_mandate(self, mandate_id: str) -> dict[str, str]:
        """DD mandate cancellation — always HITL (I-27, PSD2 Art.79)."""
        return self._dd_engine.cancel_mandate(mandate_id)

    def get_upcoming_payments(self, customer_id: str, days_ahead: int = 7) -> dict[str, object]:
        return self._executor.get_upcoming_payments(customer_id, days_ahead)

    def get_failure_report(self, customer_id: str) -> dict[str, object]:
        return self._failure_handler.get_customer_failures(customer_id)

    def record_payment_failure(
        self,
        payment_id: str,
        payment_type: PaymentType | str,
        failure_code: FailureCode | str,
        failure_reason: str,
        customer_id: str = "",
    ) -> dict[str, object]:
        pt = payment_type if isinstance(payment_type, PaymentType) else PaymentType(payment_type)
        fc = failure_code if isinstance(failure_code, FailureCode) else FailureCode(failure_code)
        result = self._failure_handler.record_failure(
            payment_id=payment_id,
            payment_type=pt,
            failure_code=fc,
            failure_reason=failure_reason,
            customer_id=customer_id,
        )
        notif = self._notifier.send_failure_alert(
            failure_id=str(result["failure_id"]),
            payment_id=payment_id,
            failure_code=fc.value,
        )
        return {**result, "notification_status": notif.get("status", "QUEUED")}
