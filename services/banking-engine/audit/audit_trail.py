"""
Banking Engine — Append-Only Audit Trail (Sandbox Stub)
Sprint B-5 | I-24: NEVER delete audit records.

Sandbox target: local JSONL file.
Production target: pgAudit / ClickHouse (wired via AuditPort Protocol DI).
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import threading
from typing import Any
import uuid

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Default sandbox path — override via BANKING_ENGINE_AUDIT_PATH env var.
# Production: replaced by ClickHouse / pgAudit adapter.
_DEFAULT_AUDIT_PATH: Path = Path.home() / ".banxe-sandbox" / "banking-engine-audit.jsonl"

SANDBOX_AUDIT_PATH: Path = _DEFAULT_AUDIT_PATH

_LOCK: threading.Lock = threading.Lock()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def write_audit_record(
    entity_type: str,
    entity_id: str,
    from_state: str,
    to_state: str,
    actor: str,
    metadata: dict[str, Any] | None = None,
    path_override: Path | None = None,
) -> str:
    """
    Append one immutable audit record.

    Returns the event_id (UUID4 string) of the written record.
    Thread-safe. File is opened in append mode — records are never overwritten.

    I-24: This function NEVER modifies or deletes existing records.
    """
    target = path_override if path_override is not None else SANDBOX_AUDIT_PATH
    record: dict[str, Any] = {
        "event_id": str(uuid.uuid4()),
        "timestamp": datetime.now(UTC).isoformat(),
        "entity_type": entity_type,
        "entity_id": entity_id,
        "from_state": from_state,
        "to_state": to_state,
        "actor": actor,
        "metadata": metadata or {},
    }
    with _LOCK:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    return record["event_id"]


def read_audit_records(
    path_override: Path | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    Read audit records from the JSONL file (sandbox only).

    Filters by entity_type and/or entity_id when provided.
    Returns an empty list if the file does not exist.
    Production: query ClickHouse / pgAudit instead.
    """
    target = path_override if path_override is not None else SANDBOX_AUDIT_PATH
    if not target.exists():
        return []
    records: list[dict[str, Any]] = []
    with _LOCK:
        for line in target.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if entity_type is not None and record.get("entity_type") != entity_type:
                continue
            if entity_id is not None and record.get("entity_id") != entity_id:
                continue
            records.append(record)
    return records
