"""OffsiteUploadPort — abstract offsite-replication interface (ADR-029 Step 5).

Defines the port for shipping a finished local backup file to an offsite
object store (MinIO on evo2 per ADR-029 §1, or any S3-compatible target).

Concrete adapters:
  InMemoryOffsiteAdapter   — deterministic dev/test double (this PR)
  MinIOOffsiteAdapter      — real S3/MinIO upload (deferred to real MinIO
                             integration step, currently raises
                             NotImplementedError at factory resolution time)

Pure typing; no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class UploadResult:
    """Outcome of a single offsite-upload attempt.

    Fields:
      success:      True if the file was accepted by the offsite target.
      remote_uri:   destination URI (e.g. "s3://banxe-pg-backups/keycloak/...").
      size_bytes:   byte count read from the local file, None if the read
                    failed or the upload never reached the read step.
      uploaded_at:  epoch seconds when the upload result was finalised.
      error:        human-readable error if !success; None on success.
    """

    success: bool
    remote_uri: str
    size_bytes: int | None
    uploaded_at: float
    error: str | None = None


@dataclass(frozen=True)
class OffsiteObject:
    """A single object stored offsite. Used by list_objects to enumerate."""

    uri: str
    size_bytes: int
    uploaded_at: float


class OffsiteUploadPort(Protocol):
    """Port for ADR-029 §1 offsite replication of backup dumps."""

    def upload(self, local_path: str, remote_uri: str) -> UploadResult:
        """Read `local_path` and ship its contents to `remote_uri`.

        MUST NOT raise on transport failure — return UploadResult(success=False).
        May raise only on programmer error (invalid argument types).
        """
        ...

    def list_objects(self, prefix: str) -> list[OffsiteObject]:
        """List all objects whose URI starts with `prefix`, sorted by
        uploaded_at descending (most recent first)."""
        ...
