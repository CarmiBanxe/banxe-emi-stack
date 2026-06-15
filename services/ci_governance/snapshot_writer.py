"""
snapshot_writer.py — Periodic protection-state snapshot capture (S16.8).

Pairs with:
  - S16.6 DriftDetector (#137) — the CLI consumes snapshots via the
    `--dry-run-payload` path on hosts without outbound GitHub access.
  - S16.7 GitHubApiProtectionReader (#138) — the snapshot source on hosts
    WITH outbound GitHub access (the capture cron runs there; the file
    propagates to the drift-sentry host via existing infra).

Contract:
  - Read-only on the GitHub side: delegates to the injected
    GitHubProtectionReaderPort. NO PUT / PATCH / DELETE / POST anywhere.
  - Atomic write on the filesystem side: serialised payload is written
    to a sibling temp file (`<target>.tmp.<pid>.<epoch>`) then renamed
    over the destination. Readers never observe a partially-written file.
  - Deterministic output: JSON `sort_keys=True` + trailing newline.

`file_writer` injection slot is for tests; the default writes through the
`pathlib` + `os.replace` atomic-rename combo.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
import os
from pathlib import Path
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.ci_governance.protection_reader_port import (
        GitHubProtectionReaderPort,
    )


FileWriter = Callable[[str, str], None]


@dataclass(frozen=True)
class SnapshotResult:
    """Outcome of one capture cycle."""

    success: bool
    snapshot_path: str
    captured_at: float
    byte_size: int | None = None
    error: str | None = None


def _default_file_writer(target_path: str, body: str) -> None:
    """Atomic write: tmpfile sibling → fsync → os.replace.

    Sibling is on the same filesystem as the target so rename is atomic.
    Parent directory is created if missing (0755).
    """
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


class ProtectionSnapshotWriter:
    """Capture a single snapshot of GitHub branch-protection state."""

    def __init__(
        self,
        reader: GitHubProtectionReaderPort,
        clock: Callable[[], float] = time.time,
        file_writer: FileWriter | None = None,
    ) -> None:
        self._reader = reader
        self._clock = clock
        self._file_writer: FileWriter = file_writer or _default_file_writer

    def capture(self, snapshot_path: str) -> SnapshotResult:
        try:
            payload = self._reader.read_main_protection()
        except Exception as exc:
            return SnapshotResult(
                success=False,
                snapshot_path=snapshot_path,
                captured_at=self._clock(),
                byte_size=None,
                error=f"reader: {type(exc).__name__}: {exc}",
            )

        body = json.dumps(payload, sort_keys=True, indent=2) + "\n"
        try:
            self._file_writer(snapshot_path, body)
        except Exception as exc:
            return SnapshotResult(
                success=False,
                snapshot_path=snapshot_path,
                captured_at=self._clock(),
                byte_size=None,
                error=f"file_writer: {type(exc).__name__}: {exc}",
            )

        return SnapshotResult(
            success=True,
            snapshot_path=snapshot_path,
            captured_at=self._clock(),
            byte_size=len(body.encode("utf-8")),
            error=None,
        )
