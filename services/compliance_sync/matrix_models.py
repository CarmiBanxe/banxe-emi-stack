"""
services/compliance_sync/matrix_models.py
Pydantic models for Compliance Matrix Auto-Sync (IL-CMS-01).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel


class ArtifactStatus(str, Enum):
    DONE = "DONE"
    IN_PROGRESS = "IN_PROGRESS"
    NOT_STARTED = "NOT_STARTED"
    BLOCKED = "BLOCKED"


class MatrixEntry(BaseModel):
    block: str
    item_id: str
    description: str
    expected_artifact: str
    actual_path: str | None = None
    test_count: int = 0
    status: ArtifactStatus = ArtifactStatus.NOT_STARTED

    model_config = {"frozen": True}


class ComplianceMatrixReport(BaseModel):
    entries: list[MatrixEntry]
    scanned_at: str
    coverage_pct: str  # Decimal as string (I-01)
    not_started_count: int
    done_count: int
    blocked_count: int

    model_config = {"frozen": True}

    @classmethod
    def build(cls, entries: list[MatrixEntry]) -> ComplianceMatrixReport:
        total = len(entries)
        done = sum(1 for e in entries if e.status == ArtifactStatus.DONE)
        not_started = sum(1 for e in entries if e.status == ArtifactStatus.NOT_STARTED)
        blocked = sum(1 for e in entries if e.status == ArtifactStatus.BLOCKED)
        pct = (
            (Decimal(done) / Decimal(total) * Decimal("100")).quantize(Decimal("0.1"))
            if total
            else Decimal("0")
        )
        return cls(
            entries=entries,
            scanned_at=datetime.now(UTC).isoformat(),
            coverage_pct=str(pct),
            not_started_count=not_started,
            done_count=done,
            blocked_count=blocked,
        )
