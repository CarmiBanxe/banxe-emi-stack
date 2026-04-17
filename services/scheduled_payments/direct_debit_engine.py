"""
services/scheduled_payments/direct_debit_engine.py — DD mandate management (Bacs/AUDDIS)
IL-SOD-01 | Phase 32 | banxe-emi-stack
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from decimal import Decimal
import uuid

from services.scheduled_payments.models import (
    DDMandate,
    DDMandatePort,
    DDStatus,
    DirectDebit,
    InMemoryDDMandateStore,
)


class DirectDebitEngine:
    def __init__(self, mandate_store: DDMandatePort | None = None) -> None:
        self._store = mandate_store or InMemoryDDMandateStore()
        self._dd_records: dict[str, DirectDebit] = {}

    def create_mandate(
        self,
        customer_id: str,
        creditor_id: str,
        creditor_name: str,
        scheme_ref: str,
        service_user_number: str,
    ) -> dict[str, str]:
        mandate = DDMandate(
            mandate_id=str(uuid.uuid4()),
            customer_id=customer_id,
            creditor_id=creditor_id,
            creditor_name=creditor_name,
            scheme_ref=scheme_ref,
            service_user_number=service_user_number,
            status=DDStatus.PENDING,
            created_at=datetime.now(UTC),
        )
        self._store.save(mandate)
        return {
            "mandate_id": mandate.mandate_id,
            "customer_id": customer_id,
            "creditor_name": creditor_name,
            "status": DDStatus.PENDING.value,
        }

    def authorise_mandate(self, mandate_id: str) -> dict[str, str]:
        mandate = self._store.get(mandate_id)
        if mandate is None:
            raise ValueError(f"Mandate not found: {mandate_id}")
        if mandate.status != DDStatus.PENDING:
            raise ValueError(f"Mandate {mandate_id} is not PENDING")
        now = datetime.now(UTC)
        updated = dataclasses.replace(mandate, status=DDStatus.AUTHORISED, authorised_at=now)
        self._store.update(updated)
        return {
            "mandate_id": mandate_id,
            "status": DDStatus.AUTHORISED.value,
            "authorised_at": now.isoformat(),
        }

    def activate_mandate(self, mandate_id: str) -> dict[str, str]:
        mandate = self._store.get(mandate_id)
        if mandate is None:
            raise ValueError(f"Mandate not found: {mandate_id}")
        if mandate.status != DDStatus.AUTHORISED:
            raise ValueError(f"Mandate {mandate_id} must be AUTHORISED to activate")
        self._store.update(dataclasses.replace(mandate, status=DDStatus.ACTIVE))
        return {"mandate_id": mandate_id, "status": DDStatus.ACTIVE.value}

    def cancel_mandate(self, mandate_id: str) -> dict[str, str]:
        """Mandate cancellation disputes require HITL (I-27, PSD2 Art.79)."""
        mandate = self._store.get(mandate_id)
        if mandate is None:
            raise ValueError(f"Mandate not found: {mandate_id}")
        if mandate.status == DDStatus.CANCELLED:
            raise ValueError(f"Mandate {mandate_id} already cancelled")
        return {
            "status": "HITL_REQUIRED",
            "mandate_id": mandate_id,
            "reason": "dd_mandate_cancellation_requires_human_approval",
            "fca_ref": "PSD2 Art.79 unconditional refund rights",
        }

    def confirm_cancel_mandate(self, mandate_id: str) -> dict[str, str]:
        """Apply cancellation after HITL approval."""
        mandate = self._store.get(mandate_id)
        if mandate is None:
            raise ValueError(f"Mandate not found: {mandate_id}")
        now = datetime.now(UTC)
        updated = dataclasses.replace(mandate, status=DDStatus.CANCELLED, cancelled_at=now)
        self._store.update(updated)
        return {
            "mandate_id": mandate_id,
            "status": DDStatus.CANCELLED.value,
            "cancelled_at": now.isoformat(),
        }

    def collect(self, mandate_id: str, amount: Decimal) -> dict[str, str]:
        mandate = self._store.get(mandate_id)
        if mandate is None:
            raise ValueError(f"Mandate not found: {mandate_id}")
        if mandate.status != DDStatus.ACTIVE:
            raise ValueError(f"Mandate {mandate_id} is not ACTIVE")
        if amount <= Decimal("0"):
            raise ValueError("Collection amount must be positive")
        now = datetime.now(UTC)
        dd = DirectDebit(
            dd_id=str(uuid.uuid4()),
            mandate_id=mandate_id,
            customer_id=mandate.customer_id,
            creditor_id=mandate.creditor_id,
            creditor_name=mandate.creditor_name,
            amount=amount,
            status=DDStatus.ACTIVE,
            created_at=now,
            last_executed_at=now,
        )
        self._dd_records[dd.dd_id] = dd
        return {
            "dd_id": dd.dd_id,
            "mandate_id": mandate_id,
            "amount": str(amount),
            "status": "COLLECTED",
        }

    def list_mandates(self, customer_id: str) -> dict[str, object]:
        mandates = self._store.list_by_customer(customer_id)
        return {
            "customer_id": customer_id,
            "mandates": [
                {
                    "mandate_id": m.mandate_id,
                    "creditor_name": m.creditor_name,
                    "status": m.status.value,
                    "scheme_ref": m.scheme_ref,
                }
                for m in mandates
            ],
            "count": len(mandates),
        }
