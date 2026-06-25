"""K-gabriel — FCA Gabriel/RegData regulatory-returns governance layer.

Orchestrates: schedule → deadline-track → validate → HITL sign-off → submit.

FCA refs:
  SUP 16.12R  — Gabriel return filing obligations
  CASS 7.15R  — Monthly FIN060 safeguarding return
  PS23/3 §5   — Safeguarding breach notification within 48h

I-27: ReturnsGovernor PROPOSES drafts; human APPROVES before GabrielSubmissionPort fires.
I-24: Append-only submission audit, TTL ≥ 5 years (I-08).
"""

from services.gabriel.gabriel_models import (
    DeadlineStatus,
    GabrielAuditEntry,
    GabrielReturnStatus,
    GabrielReturnType,
    ReturnSchedule,
    SubmissionRecord,
)
from services.gabriel.returns_governor import ReturnsGovernor

__all__ = [
    "GabrielReturnType",
    "GabrielReturnStatus",
    "SubmissionRecord",
    "ReturnSchedule",
    "DeadlineStatus",
    "GabrielAuditEntry",
    "ReturnsGovernor",
]
