"""
services/experiment_copilot/store/audit_trail.py — Append-only audit log
IL-CEC-01 | banxe-emi-stack

FCA requirement: 7-year retention. Audit entries are NEVER deleted or modified.
Format: JSONL (one JSON object per line).
Location: data/audit/experiments.jsonl
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
import logging
from pathlib import Path
from typing import Any
import uuid

from pydantic import BaseModel, Field

logger = logging.getLogger("banxe.experiment_copilot.audit")


class AuditEntry(BaseModel):
    """Single audit log entry — immutable once written."""

    entry_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    actor: str  # "claude-code" | "human:<name>" | "system"
    action: str  # "experiment.created" | "experiment.approved" | etc.
    experiment_id: str
    details: dict[str, Any] = Field(default_factory=dict)
    source_ip: str | None = None


class AuditTrail:
    """Append-only JSONL audit trail for compliance experiments.

    Invariant: entries are NEVER deleted or modified (I-24).
    Deleting entries is a compliance violation.
    """

    def __init__(self, log_path: str = "data/audit/experiments.jsonl") -> None:
        self._path = Path(log_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    # ── Write (append-only) ────────────────────────────────────────────────

    def log(
        self,
        actor: str,
        action: str,
        experiment_id: str,
        details: dict[str, Any] | None = None,
    ) -> AuditEntry:
        """Append a new audit entry. Returns the created entry."""
        entry = AuditEntry(
            actor=actor,
            action=action,
            experiment_id=experiment_id,
            details=details or {},
        )
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(entry.model_dump_json() + "\n")
        logger.info("AUDIT actor=%s action=%s experiment=%s", actor, action, experiment_id)
        return entry

    # ── Read ────────────────────────────────────────────────────────────────

    def get_entries(self, experiment_id: str | None = None) -> list[AuditEntry]:
        """Return all audit entries, optionally filtered by experiment ID."""
        if not self._path.exists():
            return []
        entries: list[AuditEntry] = []
        with open(self._path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = AuditEntry.model_validate(json.loads(line))
                    if experiment_id is None or entry.experiment_id == experiment_id:
                        entries.append(entry)
                except Exception as exc:
                    logger.warning("Malformed audit entry: %s", exc)
        return entries

    def get_entry_count(self, experiment_id: str | None = None) -> int:
        return len(self.get_entries(experiment_id))

    def export_to_clickhouse_rows(self, experiment_id: str | None = None) -> list[dict[str, Any]]:
        """Return rows suitable for ClickHouse INSERT."""
        return [
            {
                "entry_id": e.entry_id,
                "timestamp": e.timestamp.isoformat(),
                "actor": e.actor,
                "action": e.action,
                "experiment_id": e.experiment_id,
                "details": json.dumps(e.details),
            }
            for e in self.get_entries(experiment_id)
        ]

    # ── Safety guard ────────────────────────────────────────────────────────

    def delete_entries(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover
        """BLOCKED — audit entries are immutable (I-24)."""
        raise RuntimeError(
            "Audit trail entries cannot be deleted. This is a compliance invariant (I-24)."
        )
