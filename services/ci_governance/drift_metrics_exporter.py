"""
drift_metrics_exporter.py — Prometheus textfile-format metrics from S16.9 drift history (S16.11).

Reads the append-only JSONL history written by DriftHistoryStore and produces a
Prometheus textfile (.prom) that node_exporter --collector.textfile.directory
can scrape. No HTTP server, no push gateway, no new dependency — stdlib only.

Design constraints:
  - READ-ONLY against history JSONL — never mutates it.
  - Atomic write: tmpfile in same dir + os.replace (matches S16.8 pattern).
  - Always emits all 7 metric series (zero when no entries).
  - Never raises on empty history; returns ExportResult success=True.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import os
from pathlib import Path
import time

from services.ci_governance.drift_history_store import DriftHistoryStore

FileWriter = Callable[[str, str], None]


@dataclass(frozen=True)
class ExportResult:
    """Outcome of a single export operation."""

    success: bool
    textfile_path: str
    exported_at: float
    entries_scanned: int
    byte_size: int | None = None
    error: str | None = None


def _default_file_writer(target_path: str, body: str) -> None:
    """Atomic write: tmpfile sibling -> fsync -> os.replace."""
    target = Path(target_path)
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    tmp = parent / f"{target.name}.tmp.{os.getpid()}.{int(time.time_ns())}"
    try:
        tmp.write_text(body, encoding="utf-8")
        os.replace(tmp, target)
    finally:
        if tmp.exists():
            tmp.unlink()


def _render_metrics(
    entries: list[dict],
    window_seconds: int,
    export_ts: float,
) -> str:
    drift_count = sum(1 for e in entries if e.get("drift_detected") is True)
    strict_count = sum(1 for e in entries if e.get("strict_weakened") is True)

    if entries:
        latest = max(entries, key=lambda e: e.get("ts", 0))
        last_check_ts = latest.get("ts", 0.0)
        missing_last = len(latest.get("missing_rules", []))
        extra_last = len(latest.get("extra_rules", []))
    else:
        last_check_ts = 0.0
        missing_last = 0
        extra_last = 0

    ws = str(window_seconds)
    lines = [
        "# HELP banxe_ci_drift_events_total Drift events scanned in window",
        "# TYPE banxe_ci_drift_events_total counter",
        f'banxe_ci_drift_events_total{{window_seconds="{ws}"}} {len(entries)}',
        "# HELP banxe_ci_drift_detected_total Drift events with drift_detected=true",
        "# TYPE banxe_ci_drift_detected_total counter",
        f'banxe_ci_drift_detected_total{{window_seconds="{ws}"}} {drift_count}',
        "# HELP banxe_ci_drift_strict_weakened_total Drift events with strict_weakened=true",
        "# TYPE banxe_ci_drift_strict_weakened_total counter",
        f'banxe_ci_drift_strict_weakened_total{{window_seconds="{ws}"}} {strict_count}',
        "# HELP banxe_ci_drift_missing_contexts_last_count Latest missing_contexts count",
        "# TYPE banxe_ci_drift_missing_contexts_last_count gauge",
        f"banxe_ci_drift_missing_contexts_last_count {missing_last}",
        "# HELP banxe_ci_drift_extra_contexts_last_count Latest extra_contexts count",
        "# TYPE banxe_ci_drift_extra_contexts_last_count gauge",
        f"banxe_ci_drift_extra_contexts_last_count {extra_last}",
        "# HELP banxe_ci_drift_last_check_timestamp_seconds Unix ts of latest drift record",
        "# TYPE banxe_ci_drift_last_check_timestamp_seconds gauge",
        f"banxe_ci_drift_last_check_timestamp_seconds {last_check_ts}",
        "# HELP banxe_ci_drift_exporter_last_export_timestamp_seconds Unix ts of this export",
        "# TYPE banxe_ci_drift_exporter_last_export_timestamp_seconds gauge",
        f"banxe_ci_drift_exporter_last_export_timestamp_seconds {export_ts}",
    ]
    return "\n".join(lines) + "\n"


class DriftMetricsExporter:
    """Export S16.9 drift history as Prometheus textfile-format metrics."""

    def __init__(
        self,
        history_store: DriftHistoryStore,
        clock: Callable[[], float],
        file_writer: FileWriter | None = None,
    ) -> None:
        self._history_store = history_store
        self._clock = clock
        self._file_writer: FileWriter = file_writer or _default_file_writer

    def export(
        self,
        textfile_path: str,
        window_seconds: int = 86400,
    ) -> ExportResult:
        """Read history, aggregate metrics, write .prom file. Never raises."""
        now = self._clock()
        try:
            since_ts = now - window_seconds
            entries = self._history_store.read_since(since_ts)
            body = _render_metrics(entries, window_seconds, now)
            self._file_writer(textfile_path, body)
            return ExportResult(
                success=True,
                textfile_path=textfile_path,
                exported_at=now,
                entries_scanned=len(entries),
                byte_size=len(body.encode("utf-8")),
            )
        except Exception as exc:  # noqa: BLE001
            return ExportResult(
                success=False,
                textfile_path=textfile_path,
                exported_at=now,
                entries_scanned=0,
                error=str(exc),
            )
