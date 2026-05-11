"""InMemoryOffsiteAdapter — deterministic dev/test double (ADR-029 Step 5).

In-process implementation of OffsiteUploadPort. No network. No real S3.
File reads are routed through an injected callable so unit tests can supply
synthetic bytes without touching the filesystem.

Programmable failure modes (constructor arg `failure_mode`):
  "success" → upload returns UploadResult(success=True)  [default]
  "fail"    → upload returns UploadResult(success=False, error="injected fail")
  "raise"   → file_reader raise is mapped to success=False; an injected
              transport-level RuntimeError is raised before file read

These knobs let smoke + integration tests assert backup-chain behaviour under
the offsite tier's three classes of failure.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import time

from services.backup.offsite_upload_port import (
    OffsiteObject,
    OffsiteUploadPort,
    UploadResult,
)

FailureMode = str  # "success" | "fail" | "raise"


def _default_file_reader(path: str) -> bytes:
    return Path(path).read_bytes()


class InMemoryOffsiteAdapter(OffsiteUploadPort):
    """In-memory OffsiteUploadPort for tests + sandbox dev."""

    def __init__(
        self,
        clock: Callable[[], float] = time.time,
        file_reader: Callable[[str], bytes] | None = None,
        failure_mode: FailureMode = "success",
    ) -> None:
        if failure_mode not in ("success", "fail", "raise"):
            raise ValueError(
                f"failure_mode must be one of 'success'/'fail'/'raise'; got {failure_mode!r}"
            )
        self._objects: dict[str, OffsiteObject] = {}
        self._clock = clock
        self._file_reader = file_reader or _default_file_reader
        self._failure_mode = failure_mode

    def upload(self, local_path: str, remote_uri: str) -> UploadResult:
        if self._failure_mode == "raise":
            raise RuntimeError(f"injected transport error for {remote_uri}")

        try:
            data = self._file_reader(local_path)
        except Exception as exc:
            return UploadResult(
                success=False,
                remote_uri=remote_uri,
                size_bytes=None,
                uploaded_at=self._clock(),
                error=f"file_reader: {type(exc).__name__}: {exc}",
            )

        if self._failure_mode == "fail":
            return UploadResult(
                success=False,
                remote_uri=remote_uri,
                size_bytes=len(data),
                uploaded_at=self._clock(),
                error="injected fail",
            )

        now = self._clock()
        obj = OffsiteObject(uri=remote_uri, size_bytes=len(data), uploaded_at=now)
        self._objects[remote_uri] = obj
        return UploadResult(
            success=True,
            remote_uri=remote_uri,
            size_bytes=obj.size_bytes,
            uploaded_at=now,
            error=None,
        )

    def list_objects(self, prefix: str) -> list[OffsiteObject]:
        matching = [obj for uri, obj in self._objects.items() if uri.startswith(prefix)]
        matching.sort(key=lambda o: o.uploaded_at, reverse=True)
        return matching
