"""Backup subsystem — pg_dump-based backup rotation (ADR-029, G-OPS-01/02)."""

from services.backup.backup_port import (
    BackupMetadata,
    BackupPort,
    BackupResult,
    RestoreResult,
    RotationResult,
)
from services.backup.factory import BackupConfig, BackupDisabledError, get_backup_adapter
from services.backup.pg_backup_adapter import PgDumpBackupAdapter

__all__ = [
    "BackupConfig",
    "BackupDisabledError",
    "BackupMetadata",
    "BackupPort",
    "BackupResult",
    "PgDumpBackupAdapter",
    "RestoreResult",
    "RotationResult",
    "get_backup_adapter",
]
