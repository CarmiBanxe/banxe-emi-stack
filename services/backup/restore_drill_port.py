"""RestoreDrillPort — abstract restore-drill interface (ADR-029, G-OPS-02).

Defines the port for weekly automated restore-drill operations: pull a
known backup, restore it into a throwaway database, count rows in the
canonical validation table, and report the outcome.

Per ADR-029 §Implementation-Plan item 4: validate restores by row-count
on the `cases` table for banxe-marble-postgres. Concrete adapters wrap
pg_restore/psql/dropdb subprocesses (LocalRestoreDrillAdapter) or
container-based drill targets (future).

Pure typing; no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class DrillResult:
    """Outcome of a single restore-drill cycle.

    Fields:
      success:           True if restore + validation completed without error.
      instance:          logical instance name (e.g. "banxe-marble-postgres").
      backup_uri:        the URI that was restored (local path or s3://...).
      restored_at:       epoch seconds when restore completed.
      row_count:         row count from validation_table query, None if
                         validation step was not reached.
      validation_table:  table queried for row count (None on early failure).
      error:             human-readable error if !success; None on success.
    """

    success: bool
    instance: str
    backup_uri: str
    restored_at: float
    row_count: int | None = None
    validation_table: str | None = None
    error: str | None = None


class RestoreDrillPort(Protocol):
    """Port for weekly restore drill (ADR-029 §4 / G-OPS-02)."""

    def run_drill(
        self,
        instance_name: str,
        backup_uri: str,
        target_db: str | None = None,
    ) -> DrillResult:
        """Restore `backup_uri` into a throwaway DB and validate by row count.

        Args:
          instance_name: logical source instance (for the result label).
          backup_uri:    pg_restore-compatible URI (local path).
          target_db:     optional explicit throwaway DB name; if None, the
                         adapter generates one based on its drill_db_prefix
                         + injected clock.
        """
        ...
