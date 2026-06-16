"""BackupPort — abstract backup interface (ADR-029, G-OPS-01/02).

Defines the port for PostgreSQL backup operations. Concrete adapters
(PgDumpBackupAdapter) implement this protocol for pg_dump/pg_restore.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class BackupResult:
    """Result of a backup operation."""

    success: bool
    path: str
    timestamp: datetime
    size_bytes: int
    error: str | None = None


@dataclass(frozen=True)
class RestoreResult:
    """Result of a restore operation."""

    success: bool
    db_name: str
    backup_path: str
    timestamp: datetime
    error: str | None = None


@dataclass(frozen=True)
class BackupMetadata:
    """Metadata for an existing backup file."""

    path: str
    db_name: str
    timestamp: datetime
    size_bytes: int


@dataclass(frozen=True)
class RotationResult:
    """Result of a rotation (cleanup) operation."""

    success: bool
    kept: int
    deleted: int
    freed_bytes: int
    error: str | None = None


class BackupPort(Protocol):
    """Abstract port for PostgreSQL backup operations (ADR-029)."""

    def backup(self, db_name: str) -> BackupResult: ...

    def restore(self, db_name: str, backup_path: str) -> RestoreResult: ...

    def list_backups(self, db_name: str) -> list[BackupMetadata]: ...

    def rotate(self, db_name: str, keep_last: int) -> RotationResult: ...
