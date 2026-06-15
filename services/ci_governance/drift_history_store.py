"""
drift_history_store.py — Append-only JSONL history for DriftResult outcomes (S16.9).

Persists each DriftResult from S16.6 detect_drift() as a single JSON line so
operators can audit drift events over time without re-running detection.

Design constraints:
  - Append-only: no deletes, no updates, no truncate.
  - Cross-process safe: fcntl.flock(LOCK_EX) during write.
  - Atomic line: single write() call after serialisation.
  - read_all / read_since skip malformed lines silently.
"""

from __future__ import annotations

from collections.abc import Callable
import dataclasses
from dataclasses import dataclass
import fcntl
import json
import os
from pathlib import Path

from services.ci_governance.drift_detector import DriftResult


@dataclass(frozen=True)
class AppendResult:
    """Outcome of a single append operation."""

    success: bool
    history_path: str
    appended_at: float
    bytes_written: int | None = None
    error: str | None = None


def _default_file_appender(path: str, line: str) -> int:
    """Append *line* to *path* under an exclusive flock; return bytes written."""
    parent = Path(path).parent
    parent.mkdir(parents=True, exist_ok=True)

    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        encoded = line.encode("utf-8")
        os.write(fd, encoded)
        return len(encoded)
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


class DriftHistoryStore:
    """Append-only JSONL store for drift detection results."""

    def __init__(
        self,
        history_path: str,
        clock: Callable[[], float],
        file_appender: Callable[[str, str], int] | None = None,
    ) -> None:
        self._history_path = history_path
        self._clock = clock
        self._file_appender = file_appender or _default_file_appender

    def append_result(self, result: DriftResult) -> AppendResult:
        """Serialise *result* and append one JSONL line. Never raises."""
        now = self._clock()
        try:
            record = dataclasses.asdict(result)
            record["ts"] = now
            line = json.dumps(record, default=str, separators=(",", ":")) + "\n"
            written = self._file_appender(self._history_path, line)
            return AppendResult(
                success=True,
                history_path=self._history_path,
                appended_at=now,
                bytes_written=written,
            )
        except Exception as exc:  # noqa: BLE001
            return AppendResult(
                success=False,
                history_path=self._history_path,
                appended_at=now,
                error=str(exc),
            )

    def read_all(self, limit: int | None = None) -> list[dict]:
        """Return well-formed entries in file order; skip malformed lines."""
        path = Path(self._history_path)
        if not path.is_file():
            return []
        entries: list[dict] = []
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                obj = json.loads(stripped)
            except (json.JSONDecodeError, ValueError):
                continue
            if not isinstance(obj, dict):
                continue
            entries.append(obj)
            if limit is not None and len(entries) >= limit:
                break
        return entries

    def read_since(self, since_ts: float) -> list[dict]:
        """Return entries where ts >= *since_ts* (inclusive lower bound)."""
        return [e for e in self.read_all() if e.get("ts", 0) >= since_ts]
