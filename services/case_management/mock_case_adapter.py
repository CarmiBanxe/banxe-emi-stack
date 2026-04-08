"""
services/case_management/mock_case_adapter.py — In-memory Mock Case Adapter
IL-059 | EU AI Act Art.14 | banxe-emi-stack

Used for development and tests when Marble is not available.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict

from services.case_management.case_port import (
    CaseOutcome,
    CaseRequest,
    CaseResult,
    CaseStatus,
)

logger = logging.getLogger(__name__)


class MockCaseAdapter:
    """
    In-memory mock implementation of CaseManagementPort.
    All cases stored in self._cases dict (case_id → CaseResult).
    Idempotent on case_reference: same reference → same case_id.
    """

    def __init__(self) -> None:
        self._cases: Dict[str, CaseResult] = {}
        self._reference_index: Dict[str, str] = {}  # case_reference → case_id

    def create_case(self, request: CaseRequest) -> CaseResult:
        # Idempotency: return existing if already created
        if request.case_reference in self._reference_index:
            existing_id = self._reference_index[request.case_reference]
            logger.info(
                "MockCaseAdapter.create_case: idempotent hit ref=%s → case_id=%s",
                request.case_reference, existing_id,
            )
            return self._cases[existing_id]

        case_id = f"MOCK-CASE-{uuid.uuid4().hex[:10].upper()}"
        result = CaseResult(
            case_id=case_id,
            case_reference=request.case_reference,
            status=CaseStatus.OPEN,
            provider="mock",
            created_at=datetime.now(timezone.utc),
            url=f"http://localhost:5002/cases/{case_id}",
        )
        self._cases[case_id] = result
        self._reference_index[request.case_reference] = case_id

        logger.info(
            "MockCaseAdapter.create_case: ref=%s type=%s priority=%s → %s",
            request.case_reference, request.case_type, request.priority, case_id,
        )
        return result

    def get_case(self, case_id: str) -> CaseResult:
        if case_id not in self._cases:
            return CaseResult(
                case_id=case_id,
                case_reference="",
                status=CaseStatus.CLOSED,
                provider="mock",
                created_at=datetime.now(timezone.utc),
                url=None,
            )
        return self._cases[case_id]

    def resolve_case(
        self,
        case_id: str,
        outcome: CaseOutcome,
        notes: str = "",
    ) -> CaseResult:
        if case_id not in self._cases:
            raise KeyError(f"MockCaseAdapter: case {case_id} not found")
        result = self._cases[case_id]
        # Create a new dataclass instance with updated fields
        resolved = CaseResult(
            case_id=result.case_id,
            case_reference=result.case_reference,
            status=CaseStatus.RESOLVED,
            provider=result.provider,
            created_at=result.created_at,
            assigned_to=result.assigned_to,
            outcome=outcome,
            url=result.url,
        )
        self._cases[case_id] = resolved
        logger.info(
            "MockCaseAdapter.resolve_case: case_id=%s outcome=%s notes=%s",
            case_id, outcome, notes[:100] if notes else "",
        )
        return resolved

    def health(self) -> bool:
        return True

    # ── Test helpers ──────────────────────────────────────────────────────────

    def get_all_cases(self) -> list[CaseResult]:
        return list(self._cases.values())

    @property
    def case_count(self) -> int:
        return len(self._cases)

    def reset(self) -> None:
        self._cases.clear()
        self._reference_index.clear()
