"""Sprint 3+ Watchdog Audit Log — append-only JSONL evidence trail.

I-24: Append-only. Never delete, never overwrite entries.
Each record captures the full decision chain: classify → decide → act → verify.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import time
from typing import Protocol


@dataclass
class AuditRecord:
    """One watchdog decision — immutable evidence record."""

    timestamp: float
    target: str
    observed_state: str
    root_cause: str
    root_cause_confidence: float
    selected_action: str
    action_score: float
    autonomy_mode: str  # "AUTO" | "HITL"
    executed: bool
    verification_result: bool | None  # None = not attempted


class AuditLogPort(Protocol):
    """Protocol for watchdog audit logging (I-24 append-only contract)."""

    def record(self, entry: AuditRecord) -> None: ...


class FileAuditLog:
    """Append-only JSONL file audit log — one JSON object per line.

    Satisfies I-24: open in append mode only, never truncate or overwrite.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, entry: AuditRecord) -> None:
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(entry), default=str) + "\n")


class InMemoryAuditLog:
    """Stub audit log for unit tests — appends to an in-memory list."""

    def __init__(self) -> None:
        self.records: list[AuditRecord] = []

    def record(self, entry: AuditRecord) -> None:
        self.records.append(entry)


def make_audit_record(
    target: str,
    observed_state: str,
    root_cause: str,
    root_cause_confidence: float,
    selected_action: str,
    action_score: float,
    executed: bool,
    verification_result: bool | None,
    autonomy_mode: str = "AUTO",
) -> AuditRecord:
    """Build an AuditRecord stamped with the current UTC epoch timestamp."""
    return AuditRecord(
        timestamp=time.time(),
        target=target,
        observed_state=observed_state,
        root_cause=root_cause,
        root_cause_confidence=root_cause_confidence,
        selected_action=selected_action,
        action_score=action_score,
        autonomy_mode=autonomy_mode,
        executed=executed,
        verification_result=verification_result,
    )
