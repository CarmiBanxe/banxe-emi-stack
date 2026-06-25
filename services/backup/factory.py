"""Backup DI factory — creates configured PgDumpBackupAdapter from env (ADR-029).

Reads connection parameters and backup config from environment variables.
Feature flag BACKUP_ENABLED controls whether backup operations are active.

Usage:
    from services.backup.factory import get_backup_adapter
    adapter = get_backup_adapter()  # raises BackupDisabledError if disabled
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import os

from services.backup.in_memory_offsite_adapter import InMemoryOffsiteAdapter
from services.backup.local_restore_drill_adapter import LocalRestoreDrillAdapter
from services.backup.offsite_upload_port import OffsiteUploadPort
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


# ── ADR-029 Step 4 — Restore drill ──────────────────────────────────────────


class RestoreDrillDisabledError(Exception):
    """Raised when restore-drill operations are attempted while disabled."""


@dataclass(frozen=True)
class RestoreDrillConfig:
    """Configuration for LocalRestoreDrillAdapter, loaded from environment."""

    enabled: bool
    validation_table: str
    drill_db_prefix: str

    @classmethod
    def from_env(cls) -> RestoreDrillConfig:
        return cls(
            enabled=os.environ.get("RESTORE_DRILL_ENABLED", "false").lower() == "true",
            validation_table=os.environ.get("RESTORE_DRILL_VALIDATION_TABLE", "cases"),
            drill_db_prefix=os.environ.get("RESTORE_DRILL_DB_PREFIX", "postgres-restore-drill-"),
        )


@lru_cache(maxsize=1)
def get_restore_drill_adapter(
    config: RestoreDrillConfig | None = None,
) -> LocalRestoreDrillAdapter:
    """Create a configured LocalRestoreDrillAdapter from environment.

    Raises:
        RestoreDrillDisabledError: if RESTORE_DRILL_ENABLED is not "true".
    """
    cfg = config or RestoreDrillConfig.from_env()

    if not cfg.enabled:
        raise RestoreDrillDisabledError(
            "Restore drill operations disabled (RESTORE_DRILL_ENABLED != 'true'). "
            "Set RESTORE_DRILL_ENABLED=true in environment to enable."
        )

    return LocalRestoreDrillAdapter(
        validation_table=cfg.validation_table,
        drill_db_prefix=cfg.drill_db_prefix,
    )


# ── ADR-029 Step 5 — Offsite upload ─────────────────────────────────────────


@dataclass(frozen=True)
class OffsiteUploadConfig:
    """Configuration for the offsite upload adapter (ADR-029 §1)."""

    enabled: bool
    adapter: str  # "in_memory" | "minio"

    @classmethod
    def from_env(cls) -> OffsiteUploadConfig:
        return cls(
            enabled=os.environ.get("OFFSITE_UPLOAD_ENABLED", "false").lower() == "true",
            adapter=os.environ.get("OFFSITE_UPLOAD_ADAPTER", "in_memory"),
        )


@lru_cache(maxsize=1)
def get_offsite_upload_adapter(
    config: OffsiteUploadConfig | None = None,
) -> OffsiteUploadPort | None:
    """Resolve an OffsiteUploadPort from env, or None when disabled.

    Returns None when OFFSITE_UPLOAD_ENABLED != "true" (offsite tier is
    optional — callers that need it must check for None and gracefully
    skip the offsite step).

    OFFSITE_UPLOAD_ADAPTER:
      "in_memory" → InMemoryOffsiteAdapter (default; dev/test/sandbox)
      "minio"     → None (real MinIO adapter pending ADR-029 §1 infra step on evo2)
    """
    cfg = config or OffsiteUploadConfig.from_env()

    if not cfg.enabled:
        return None

    if cfg.adapter == "in_memory":
        return InMemoryOffsiteAdapter()

    if cfg.adapter == "minio":
        # MinIO adapter pending ADR-029 §1 infra step. Treat as disabled until provisioned.
        return None

    raise ValueError(
        f"OFFSITE_UPLOAD_ADAPTER={cfg.adapter!r}: supported values are 'in_memory' and 'minio'."
    )
