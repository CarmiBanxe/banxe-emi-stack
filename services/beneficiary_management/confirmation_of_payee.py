"""
services/beneficiary_management/confirmation_of_payee.py — CoP check (PSR 2017 mandate)
IL-BPM-01 | Phase 34 | banxe-emi-stack
"""

from __future__ import annotations

from datetime import UTC, datetime

from services.beneficiary_management.models import (
    BeneficiaryPort,
    CoPPort,
    CoPResult,
    InMemoryBeneficiaryStore,
    InMemoryCoPStore,
)

_COP_MATCH = "MATCH"
_COP_CLOSE = "CLOSE_MATCH"
_COP_NO = "NO_MATCH"


def _normalise(name: str) -> str:
    return name.strip().lower()


def _is_close_match(a: str, b: str) -> bool:
    """True if the names share at least the first word (stub for production fuzzy match)."""
    a_words = _normalise(a).split()
    b_words = _normalise(b).split()
    return bool(a_words and b_words and a_words[0] == b_words[0])


class ConfirmationOfPayee:
    def __init__(
        self,
        beneficiary_store: BeneficiaryPort | None = None,
        cop_store: CoPPort | None = None,
    ) -> None:
        self._beneficiaries = beneficiary_store or InMemoryBeneficiaryStore()
        self._cop = cop_store or InMemoryCoPStore()

    def check(self, beneficiary_id: str, expected_name: str) -> dict[str, str]:
        """PSR 2017 — Confirmation of Payee check."""
        beneficiary = self._beneficiaries.get(beneficiary_id)
        if beneficiary is None:
            raise ValueError(f"Beneficiary {beneficiary_id} not found")

        actual = beneficiary.name
        if _normalise(actual) == _normalise(expected_name):
            result = _COP_MATCH
        elif _is_close_match(actual, expected_name):
            result = _COP_CLOSE
        else:
            result = _COP_NO

        cop = CoPResult(
            result=result,
            beneficiary_id=beneficiary_id,
            expected_name=expected_name,
            matched_name=actual,
            checked_at=datetime.now(UTC),
        )
        self._cop.save(cop)
        return {
            "result": result,
            "beneficiary_id": beneficiary_id,
            "expected_name": expected_name,
            "matched_name": actual,
        }

    def get_cop_history(self, beneficiary_id: str) -> dict[str, object]:
        records = self._cop.list_by_beneficiary(beneficiary_id)
        return {
            "beneficiary_id": beneficiary_id,
            "count": len(records),
            "checks": [
                {
                    "result": r.result,
                    "expected_name": r.expected_name,
                    "matched_name": r.matched_name,
                    "checked_at": r.checked_at.isoformat(),
                }
                for r in records
            ],
        }
