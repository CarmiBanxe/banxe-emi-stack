"""
services/beneficiary_management/trusted_beneficiary.py — Trusted payee management (HITL I-27)
IL-BPM-01 | Phase 34 | banxe-emi-stack
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from decimal import Decimal
import uuid

from services.beneficiary_management.models import (
    BeneficiaryPort,
    InMemoryBeneficiaryStore,
    InMemoryTrustedBeneficiaryStore,
    TrustedBeneficiary,
    TrustedBeneficiaryPort,
)


class TrustedBeneficiaryManager:
    def __init__(
        self,
        beneficiary_store: BeneficiaryPort | None = None,
        trust_store: TrustedBeneficiaryPort | None = None,
    ) -> None:
        self._beneficiaries = beneficiary_store or InMemoryBeneficiaryStore()
        self._trust = trust_store or InMemoryTrustedBeneficiaryStore()

    def mark_trusted(
        self,
        beneficiary_id: str,
        customer_id: str,
        daily_limit: Decimal,
        approved_by: str = "",
    ) -> dict[str, object]:
        """Marking trusted always requires HITL approval (I-27)."""
        beneficiary = self._beneficiaries.get(beneficiary_id)
        if beneficiary is None:
            raise ValueError(f"Beneficiary {beneficiary_id} not found")
        if daily_limit <= Decimal("0"):
            raise ValueError("Daily limit must be positive (I-01)")
        return {
            "status": "HITL_REQUIRED",
            "beneficiary_id": beneficiary_id,
            "customer_id": customer_id,
            "daily_limit": str(daily_limit),
            "reason": "Trusted beneficiary designation requires human approval (I-27)",
        }

    def confirm_trust(
        self,
        beneficiary_id: str,
        customer_id: str,
        daily_limit: Decimal,
        approved_by: str,
    ) -> dict[str, str]:
        """Apply trust after HITL approval."""
        beneficiary = self._beneficiaries.get(beneficiary_id)
        if beneficiary is None:
            raise ValueError(f"Beneficiary {beneficiary_id} not found")
        trust = TrustedBeneficiary(
            trust_id=str(uuid.uuid4()),
            beneficiary_id=beneficiary_id,
            customer_id=customer_id,
            daily_limit=daily_limit,
            approved_by=approved_by,
            approved_at=datetime.now(UTC),
        )
        self._trust.save(trust)
        updated = dataclasses.replace(self._beneficiaries.get(beneficiary_id), trusted=True)  # type: ignore[arg-type]
        self._beneficiaries.update(updated)
        return {
            "trust_id": trust.trust_id,
            "beneficiary_id": beneficiary_id,
            "status": "TRUSTED",
            "daily_limit": str(daily_limit),
        }

    def revoke_trust(self, beneficiary_id: str) -> dict[str, str]:
        trust = self._trust.get_by_beneficiary(beneficiary_id)
        if trust is None:
            raise ValueError(f"No trust record for beneficiary {beneficiary_id}")
        revoked = dataclasses.replace(trust, is_active=False)
        self._trust.update(revoked)
        beneficiary = self._beneficiaries.get(beneficiary_id)
        if beneficiary:
            self._beneficiaries.update(dataclasses.replace(beneficiary, trusted=False))
        return {"beneficiary_id": beneficiary_id, "status": "TRUST_REVOKED"}

    def is_trusted(self, beneficiary_id: str) -> bool:
        trust = self._trust.get_by_beneficiary(beneficiary_id)
        return trust is not None and trust.is_active

    def get_daily_limit(self, beneficiary_id: str) -> dict[str, object]:
        trust = self._trust.get_by_beneficiary(beneficiary_id)
        if trust is None:
            return {"beneficiary_id": beneficiary_id, "trusted": False, "daily_limit": None}
        return {
            "beneficiary_id": beneficiary_id,
            "trusted": trust.is_active,
            "daily_limit": str(trust.daily_limit) if trust.is_active else None,
        }
