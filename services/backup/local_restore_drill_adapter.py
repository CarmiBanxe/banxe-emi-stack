"""LocalRestoreDrillAdapter — subprocess-driven restore drill (ADR-029 Step 4).

Implements RestoreDrillPort by orchestrating:

  1. createdb        → throwaway drill DB
  2. pg_restore -d   → restore the supplied backup URI into the drill DB
  3. psql -t -c      → SELECT count(*) FROM <validation_table>
  4. dropdb          → tear down the drill DB (best-effort, never raises)

All subprocesses are routed through an injected callable so unit tests
can supply a FakeSubprocessRunner. The default runner wraps
`subprocess.run` with capture_output=True, text=True.

Per ADR-029 §Implementation-Plan item 4: validation_table defaults to
"cases" (banxe-marble-postgres canonical table). Drill DB name pattern:
  f"{drill_db_prefix}{instance_name}-{int(clock())}"
"""

from __future__ import annotations

from collections.abc import Callable
import contextlib
import re
import subprocess
import time

from services.backup.restore_drill_port import DrillResult, RestoreDrillPort

SubprocessRunner = Callable[..., subprocess.CompletedProcess]

# Operator-supplied table identifier must match a strict shape before being
# interpolated into a SQL string. ADR-029 §4 only requires simple table names
# ("cases", "applicants", etc.); this rejects anything that could break out.
_VALID_TABLE_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _default_subprocess_runner(args: list[str], **kwargs: object) -> subprocess.CompletedProcess:
    # capture_output + text default on so the adapter can inspect stdout/stderr.
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("text", True)
    return subprocess.run(args, check=False, **kwargs)  # noqa: S603 — explicit check=False; caller inspects returncode


class LocalRestoreDrillAdapter(RestoreDrillPort):
    """RestoreDrillPort backed by createdb/pg_restore/psql/dropdb."""

    def __init__(
        self,
        *,
        subprocess_runner: SubprocessRunner | None = None,
        clock: Callable[[], float] = time.time,
        validation_table: str = "cases",
        psql_path: str = "psql",
        pg_restore_path: str = "pg_restore",
        createdb_path: str = "createdb",
        dropdb_path: str = "dropdb",
        drill_db_prefix: str = "postgres-restore-drill-",
    ) -> None:
        if not _VALID_TABLE_IDENT.match(validation_table):
            raise ValueError(
                f"validation_table must be a simple SQL identifier "
                f"(letters/digits/underscore, starting non-digit); got "
                f"{validation_table!r}"
            )
        self._run = subprocess_runner or _default_subprocess_runner
        self._clock = clock
        self._validation_table = validation_table
        self._psql = psql_path
        self._pg_restore = pg_restore_path
        self._createdb = createdb_path
        self._dropdb = dropdb_path
        self._db_prefix = drill_db_prefix

    def run_drill(
        self,
        instance_name: str,
        backup_uri: str,
        target_db: str | None = None,
    ) -> DrillResult:
        drill_db = target_db or f"{self._db_prefix}{instance_name}-{int(self._clock())}"

        # Step 1 — createdb
        cr = self._run([self._createdb, drill_db])
        if cr.returncode != 0:
            self._best_effort_dropdb(drill_db)
            return DrillResult(
                success=False,
                instance=instance_name,
                backup_uri=backup_uri,
                restored_at=self._clock(),
                row_count=None,
                validation_table=None,
                error=f"createdb failed (exit {cr.returncode}): {(cr.stderr or '')[:200]}",
            )

        # Step 2 — pg_restore
        rr = self._run([self._pg_restore, "--dbname", drill_db, backup_uri])
        if rr.returncode != 0:
            self._best_effort_dropdb(drill_db)
            return DrillResult(
                success=False,
                instance=instance_name,
                backup_uri=backup_uri,
                restored_at=self._clock(),
                row_count=None,
                validation_table=None,
                error=f"pg_restore failed (exit {rr.returncode}): {(rr.stderr or '')[:200]}",
            )

        # Step 3 — validation row count.
        # validation_table is asserted to match _VALID_TABLE_IDENT at __init__,
        # so direct interpolation here is safe (no user-controlled input).
        query = f"SELECT count(*) FROM {self._validation_table};"  # noqa: S608  # nosec B608 — identifier validated against _VALID_TABLE_IDENT at construction
        vr = self._run([self._psql, "-d", drill_db, "-t", "-c", query])
        if vr.returncode != 0:
            self._best_effort_dropdb(drill_db)
            return DrillResult(
                success=False,
                instance=instance_name,
                backup_uri=backup_uri,
                restored_at=self._clock(),
                row_count=None,
                validation_table=self._validation_table,
                error=f"psql count failed (exit {vr.returncode}): {(vr.stderr or '')[:200]}",
            )

        row_count = _parse_count(vr.stdout or "")
        if row_count is None:
            self._best_effort_dropdb(drill_db)
            return DrillResult(
                success=False,
                instance=instance_name,
                backup_uri=backup_uri,
                restored_at=self._clock(),
                row_count=None,
                validation_table=self._validation_table,
                error=f"could not parse row count from psql stdout: {(vr.stdout or '')[:100]!r}",
            )

        # Step 4 — best-effort cleanup
        self._best_effort_dropdb(drill_db)

        return DrillResult(
            success=True,
            instance=instance_name,
            backup_uri=backup_uri,
            restored_at=self._clock(),
            row_count=row_count,
            validation_table=self._validation_table,
            error=None,
        )

    def _best_effort_dropdb(self, drill_db: str) -> None:
        with contextlib.suppress(Exception):
            self._run([self._dropdb, "--if-exists", drill_db])


def _parse_count(stdout: str) -> int | None:
    """psql -t emits a single value with leading/trailing whitespace.

    Returns None when the stdout is empty or not an int.
    """
    stripped = stdout.strip()
    if not stripped:
        return None
    try:
        return int(stripped.splitlines()[0].strip())
    except (ValueError, IndexError):
        return None
