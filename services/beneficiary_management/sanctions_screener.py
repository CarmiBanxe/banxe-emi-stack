"""
services/beneficiary_management/sanctions_screener.py — Watchman sanctions screening adapter
IL-BPM-01 | Phase 34 | banxe-emi-stack
"""

from __future__ import annotations

from datetime import UTC, datetime
import uuid

from services.beneficiary_management.models import (
    BLOCKED_JURISDICTIONS,
    BeneficiaryPort,
    InMemoryBeneficiaryStore,
    InMemoryScreeningStore,
    ScreeningPort,
    ScreeningRecord,
    ScreeningResult,
)

# High-risk name patterns for stub PARTIAL_MATCH (in production: Moov Watchman API)
_HIGH_RISK_PATTERNS = {"test_sanctioned", "ofac_listed", "sdn_match"}


class SanctionsScreener:
    def __init__(
        self,
        beneficiary_store: BeneficiaryPort | None = None,
        screening_store: ScreeningPort | None = None,
    ) -> None:
        self._beneficiaries = beneficiary_store or InMemoryBeneficiaryStore()
        self._screening = screening_store or InMemoryScreeningStore()

    def screen(self, beneficiary_id: str) -> dict[str, str]:
        """Screen beneficiary against sanctions lists (I-02, MLR 2017 Reg.28).

        Auto-MATCH for blocked jurisdictions (I-02).
        PARTIAL_MATCH for high-risk name patterns.
        NO_MATCH otherwise (stub — production uses Moov Watchman :5001).
        """
        beneficiary = self._beneficiaries.get(beneficiary_id)
        if beneficiary is None:
            raise ValueError(f"Beneficiary {beneficiary_id} not found")

        if beneficiary.country_code in BLOCKED_JURISDICTIONS:
            result = ScreeningResult.MATCH
            details = f"Blocked jurisdiction: {beneficiary.country_code} (I-02)"
        elif beneficiary.name.lower() in _HIGH_RISK_PATTERNS:
            result = ScreeningResult.PARTIAL_MATCH
            details = "Name pattern flagged for review"
        else:
            result = ScreeningResult.NO_MATCH
            details = ""

        record = ScreeningRecord(
            record_id=str(uuid.uuid4()),
            beneficiary_id=beneficiary_id,
            result=result,
            checked_at=datetime.now(UTC),
            watchman_ref=str(uuid.uuid4()) if result != ScreeningResult.NO_MATCH else "",
            details=details,
        )
        self._screening.save(record)
        return {
            "record_id": record.record_id,
            "beneficiary_id": beneficiary_id,
            "result": result.value,
            "details": details,
        }

    def get_screening_history(self, beneficiary_id: str) -> dict[str, object]:
        records = self._screening.list_by_beneficiary(beneficiary_id)
        return {
            "beneficiary_id": beneficiary_id,
            "count": len(records),
            "records": [
                {
                    "record_id": r.record_id,
                    "result": r.result.value,
                    "checked_at": r.checked_at.isoformat(),
                }
                for r in records
            ],
        }
