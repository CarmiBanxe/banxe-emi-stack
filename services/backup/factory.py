"""Backup DI factory — creates configured PgDumpBackupAdapter from env (ADR-029).

Reads connection parameters and backup config from environment variables.
Feature flag BACKUP_ENABLED controls whether backup operations are active.

Usage:
    from services.backup.factory import get_backup_adapter
    adapter = get_backup_adapter()  # raises BackupDisabledError if disabled
"""

from __future__ import annotations

from dataclasses import dataclass
import os

from services.backup.pg_backup_adapter import PgDumpBackupAdapter


class BackupDisabledError(Exception):
    """Raised when backup operations are attempted while BACKUP_ENABLED=false."""


@dataclass(frozen=True)
class BackupConfig:
    """Configuration for PgDumpBackupAdapter, loaded from environment."""

    enabled: bool
    pg_host: str
    pg_port: int
    pg_user: str
    pg_password: str
    backup_dir: str
    retention_count: int

    @classmethod
    def from_env(cls) -> BackupConfig:
        """Load backup config from environment variables."""
        return cls(
            enabled=os.environ.get("BACKUP_ENABLED", "false").lower() == "true",
            pg_host=os.environ.get("BACKUP_PG_HOST", "localhost"),
            pg_port=int(os.environ.get("BACKUP_PG_PORT", "5432")),
            pg_user=os.environ.get("BACKUP_PG_USER", "banxe"),
            pg_password=os.environ.get("BACKUP_PG_PASSWORD", ""),
            backup_dir=os.environ.get("BACKUP_DIR", "/data/banxe/backups"),
            retention_count=int(os.environ.get("BACKUP_RETENTION_COUNT", "7")),
        )


def get_backup_adapter(config: BackupConfig | None = None) -> PgDumpBackupAdapter:
    """Create a configured PgDumpBackupAdapter from environment.

    Raises:
        BackupDisabledError: if BACKUP_ENABLED is not "true".
    """
    cfg = config or BackupConfig.from_env()

    if not cfg.enabled:
        raise BackupDisabledError(
            "Backup operations disabled (BACKUP_ENABLED != 'true'). "
            "Set BACKUP_ENABLED=true in environment to enable."
        )

    return PgDumpBackupAdapter(
        pg_host=cfg.pg_host,
        pg_port=cfg.pg_port,
        pg_user=cfg.pg_user,
        pg_password=cfg.pg_password,
        backup_dir=cfg.backup_dir,
        retention_count=cfg.retention_count,
    )
