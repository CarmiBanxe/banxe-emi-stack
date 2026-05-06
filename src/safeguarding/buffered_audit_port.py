"""BufferedAuditPort — SQLite ring-buffer for ReconAuditPort durability.

ADR-027 Option (b): SQLite WAL ring-buffer that survives ClickHouse outages.
Regulatory basis: FCA CASS 15 §15.10 / DORA Art.14(2) — every reconciliation
event must be durably recorded even when the primary audit sink is unavailable.

Invariant I-24: entries are never deleted until successfully drained to target.
"""
from __future__ import annotations

import dataclasses
import json
import logging
import sqlite3
import threading
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from src.safeguarding.audit_trail import AuditEvent

logger = logging.getLogger(__name__)

DEFAULT_BUFFER_PATH = "/tmp/banxe-audit-buffer.db"

_DDL = """
CREATE TABLE IF NOT EXISTS audit_buffer (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    event_json TEXT    NOT NULL,
    created_at TEXT    DEFAULT CURRENT_TIMESTAMP,
    drained    INTEGER DEFAULT 0
)
"""


@runtime_checkable
class _DrainTarget(Protocol):
    def log(self, event: Any) -> bool: ...


def _json_default(obj: Any) -> str:
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, Enum):
        return obj.value
    return str(obj)


class BufferedAuditPort:
    """SQLite ring-buffer conforming to ReconAuditPort Protocol. ADR-027 Option (b).

    Thread-safe: one Lock, new connection per operation (sqlite3 connections are
    not safe to share across threads).
    """

    def __init__(self, db_path: str | Path = DEFAULT_BUFFER_PATH) -> None:
        self._db_path = str(db_path)
        self._lock = threading.Lock()
        self._init_db()

    # ------------------------------------------------------------------
    # ReconAuditPort interface
    # ------------------------------------------------------------------

    def record(self, entry: Any) -> None:
        """Serialize entry to JSON and INSERT into SQLite. Never raises."""
        try:
            event_json = json.dumps(dataclasses.asdict(entry), default=_json_default)
            with self._lock:
                conn = sqlite3.connect(self._db_path)
                try:
                    conn.execute(
                        "INSERT INTO audit_buffer (event_json) VALUES (?)",
                        (event_json,),
                    )
                    conn.commit()
                finally:
                    conn.close()
        except Exception as exc:
            logger.error("BufferedAuditPort.record() failed — event NOT buffered: %s", exc)

    # ------------------------------------------------------------------
    # Drain / maintenance
    # ------------------------------------------------------------------

    def drain(self, target: _DrainTarget, batch_size: int = 100) -> int:
        """Transfer undrained events to target. Returns count drained.

        Stops on first target.log() failure (returns False or raises).
        Events are marked drained only after target.log() returns True.
        """
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            try:
                rows = conn.execute(
                    "SELECT id, event_json FROM audit_buffer "
                    "WHERE drained=0 ORDER BY id LIMIT ?",
                    (batch_size,),
                ).fetchall()
            finally:
                conn.close()

        drained = 0
        for row_id, event_json in rows:
            try:
                event = self._to_audit_event(event_json)
                success = target.log(event)
            except Exception as exc:
                logger.error("BufferedAuditPort.drain() target.log raised: %s", exc)
                break
            if not success:
                break
            with self._lock:
                conn = sqlite3.connect(self._db_path)
                try:
                    conn.execute(
                        "UPDATE audit_buffer SET drained=1 WHERE id=?", (row_id,)
                    )
                    conn.commit()
                finally:
                    conn.close()
            drained += 1
        return drained

    def pending_count(self) -> int:
        """Return count of events not yet drained."""
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            try:
                row = conn.execute(
                    "SELECT COUNT(*) FROM audit_buffer WHERE drained=0"
                ).fetchone()
                return row[0] if row else 0
            finally:
                conn.close()

    def cleanup(self, max_age_days: int = 14) -> int:
        """Delete drained rows older than max_age_days. Returns deleted count."""
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            try:
                cursor = conn.execute(
                    "DELETE FROM audit_buffer WHERE drained=1 "
                    "AND created_at < datetime('now', ? || ' days')",
                    (f"-{max_age_days}",),
                )
                conn.commit()
                return cursor.rowcount
            except Exception as exc:
                logger.error("BufferedAuditPort.cleanup() failed: %s", exc)
                return 0
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute(_DDL)
                conn.commit()
            finally:
                conn.close()

    def _to_audit_event(self, event_json: str) -> AuditEvent:
        from src.safeguarding.audit_trail import AuditEvent

        data = json.loads(event_json)
        return AuditEvent(
            event_type=data.get("action", "RECON_AUDIT"),
            entity_id=data.get("recon_id", ""),
            actor=data.get("actor", "SYSTEM"),
            payload=data,
            severity="INFO",
        )
