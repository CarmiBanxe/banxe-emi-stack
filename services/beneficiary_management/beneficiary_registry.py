"""
services/beneficiary_management/beneficiary_registry.py — Beneficiary lifecycle management
IL-BPM-01 | Phase 34 | banxe-emi-stack
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
import uuid

from services.beneficiary_management.models import (
    BLOCKED_JURISDICTIONS,
    Beneficiary,
    BeneficiaryPort,
    BeneficiaryStatus,
    BeneficiaryType,
    InMemoryBeneficiaryStore,
)


class BeneficiaryRegistry:
    def __init__(self, store: BeneficiaryPort | None = None) -> None:
        self._store = store or InMemoryBeneficiaryStore()

    def add_beneficiary(
        self,
        customer_id: str,
        beneficiary_type: BeneficiaryType,
        name: str,
        account_number: str = "",
        sort_code: str = "",
        iban: str = "",
        bic: str = "",
        currency: str = "GBP",
        country_code: str = "GB",
    ) -> dict[str, str]:
        if country_code.upper() in BLOCKED_JURISDICTIONS:
            raise ValueError(
                f"Country {country_code} is a blocked jurisdiction (I-02). "
                "Beneficiaries from sanctioned countries cannot be added."
            )
        beneficiary = Beneficiary(
            beneficiary_id=str(uuid.uuid4()),
            customer_id=customer_id,
            beneficiary_type=beneficiary_type,
            name=name,
            account_number=account_number,
            sort_code=sort_code,
            iban=iban,
            bic=bic,
            currency=currency,
            country_code=country_code.upper(),
            status=BeneficiaryStatus.PENDING,
            created_at=datetime.now(UTC),
        )
        self._store.save(beneficiary)
        return {
            "beneficiary_id": beneficiary.beneficiary_id,
            "customer_id": customer_id,
            "name": name,
            "status": BeneficiaryStatus.PENDING.value,
        }

    def verify_beneficiary(self, beneficiary_id: str) -> dict[str, str]:
        beneficiary = self._store.get(beneficiary_id)
        if beneficiary is None:
            raise ValueError(f"Beneficiary {beneficiary_id} not found")
        if beneficiary.status != BeneficiaryStatus.PENDING:
            raise ValueError(f"Beneficiary {beneficiary_id} is not PENDING")
        updated = dataclasses.replace(beneficiary, status=BeneficiaryStatus.ACTIVE)
        self._store.update(updated)
        return {
            "beneficiary_id": beneficiary_id,
            "status": BeneficiaryStatus.ACTIVE.value,
        }

    def activate_beneficiary(self, beneficiary_id: str) -> dict[str, str]:
        beneficiary = self._store.get(beneficiary_id)
        if beneficiary is None:
            raise ValueError(f"Beneficiary {beneficiary_id} not found")
        updated = dataclasses.replace(beneficiary, status=BeneficiaryStatus.ACTIVE)
        self._store.update(updated)
        return {"beneficiary_id": beneficiary_id, "status": BeneficiaryStatus.ACTIVE.value}

    def deactivate_beneficiary(self, beneficiary_id: str) -> dict[str, str]:
        beneficiary = self._store.get(beneficiary_id)
        if beneficiary is None:
            raise ValueError(f"Beneficiary {beneficiary_id} not found")
        updated = dataclasses.replace(beneficiary, status=BeneficiaryStatus.DEACTIVATED)
        self._store.update(updated)
        return {"beneficiary_id": beneficiary_id, "status": BeneficiaryStatus.DEACTIVATED.value}

    def delete_beneficiary(self, beneficiary_id: str) -> dict[str, str]:
        """Deletion always requires HITL approval (I-27)."""
        beneficiary = self._store.get(beneficiary_id)
        if beneficiary is None:
            raise ValueError(f"Beneficiary {beneficiary_id} not found")
        return {
            "status": "HITL_REQUIRED",
            "beneficiary_id": beneficiary_id,
            "reason": "Beneficiary deletion requires human approval (I-27)",
        }

    def get_beneficiary(self, beneficiary_id: str) -> dict[str, str]:
        beneficiary = self._store.get(beneficiary_id)
        if beneficiary is None:
            raise ValueError(f"Beneficiary {beneficiary_id} not found")
        return {
            "beneficiary_id": beneficiary.beneficiary_id,
            "customer_id": beneficiary.customer_id,
            "name": beneficiary.name,
            "status": beneficiary.status.value,
            "country_code": beneficiary.country_code,
            "currency": beneficiary.currency,
        }

    def list_beneficiaries(self, customer_id: str) -> dict[str, object]:
        beneficiaries = self._store.list_by_customer(customer_id)
        return {
            "customer_id": customer_id,
            "count": len(beneficiaries),
            "beneficiaries": [
                {
                    "beneficiary_id": b.beneficiary_id,
                    "name": b.name,
                    "status": b.status.value,
                }
                for b in beneficiaries
            ],
        }
