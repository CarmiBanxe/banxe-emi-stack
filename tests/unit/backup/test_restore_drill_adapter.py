"""Unit tests for LocalRestoreDrillAdapter (ADR-029 Step 4).

FakeSubprocessRunner is an in-memory subprocess.run stand-in: records every
invocation (args + kwargs) and returns programmable CompletedProcess. No real
subprocess, no real database.
"""

from __future__ import annotations

import subprocess
from typing import Any

import pytest

from services.backup.factory import (
    RestoreDrillConfig,
    RestoreDrillDisabledError,
    get_restore_drill_adapter,
)
from services.backup.local_restore_drill_adapter import LocalRestoreDrillAdapter


class FakeSubprocessRunner:
    """subprocess.run-shaped fake. Programmable per-command (first arg)."""

    def __init__(
        self,
        returncodes: dict[str, int] | None = None,
        stdouts: dict[str, str] | None = None,
        stderrs: dict[str, str] | None = None,
    ) -> None:
        self._rcs = returncodes or {}
        self._outs = stdouts or {}
        self._errs = stderrs or {}
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        self.calls.append(list(args))
        key = args[0]
        return subprocess.CompletedProcess(
            args=args,
            returncode=self._rcs.get(key, 0),
            stdout=self._outs.get(key, ""),
            stderr=self._errs.get(key, ""),
        )

    def commands_invoked(self) -> list[str]:
        return [c[0] for c in self.calls]


def _adapter(
    runner: FakeSubprocessRunner,
    *,
    clock_value: float = 1714000000.0,
    validation_table: str = "cases",
    drill_db_prefix: str = "postgres-restore-drill-",
) -> LocalRestoreDrillAdapter:
    return LocalRestoreDrillAdapter(
        subprocess_runner=runner,
        clock=lambda: clock_value,
        validation_table=validation_table,
        drill_db_prefix=drill_db_prefix,
    )


def test_run_drill_invokes_pg_restore_with_backup_uri() -> None:
    runner = FakeSubprocessRunner(stdouts={"psql": "42\n"})
    adapter = _adapter(runner)
    adapter.run_drill("banxe-marble-postgres", "/data/x.dump")
    # pg_restore was invoked with --dbname <drill_db> <backup_uri>
    pg_restore_calls = [c for c in runner.calls if c[0] == "pg_restore"]
    assert len(pg_restore_calls) == 1
    assert "--dbname" in pg_restore_calls[0]
    assert "/data/x.dump" in pg_restore_calls[0]


def test_run_drill_invokes_psql_count_on_validation_table() -> None:
    runner = FakeSubprocessRunner(stdouts={"psql": "100\n"})
    adapter = _adapter(runner, validation_table="cases")
    adapter.run_drill("inst", "/x")
    psql_calls = [c for c in runner.calls if c[0] == "psql"]
    assert len(psql_calls) == 1
    # The query string is the last -c argument
    assert any("SELECT count(*) FROM cases;" in arg for arg in psql_calls[0])


def test_run_drill_returns_success_with_row_count_on_clean_subprocess_chain() -> None:
    runner = FakeSubprocessRunner(stdouts={"psql": "  1234  \n"})
    adapter = _adapter(runner)
    res = adapter.run_drill("inst", "/x")
    assert res.success is True
    assert res.row_count == 1234
    assert res.error is None
    assert res.validation_table == "cases"
    assert res.instance == "inst"
    assert res.backup_uri == "/x"


def test_run_drill_returns_failure_when_pg_restore_subprocess_errors() -> None:
    runner = FakeSubprocessRunner(
        returncodes={"pg_restore": 1},
        stderrs={"pg_restore": "could not connect"},
    )
    adapter = _adapter(runner)
    res = adapter.run_drill("inst", "/x")
    assert res.success is False
    assert res.row_count is None
    assert res.validation_table is None
    assert "pg_restore failed" in (res.error or "")
    assert "could not connect" in (res.error or "")


def test_run_drill_returns_failure_when_psql_count_fails() -> None:
    runner = FakeSubprocessRunner(
        returncodes={"psql": 2}, stderrs={"psql": "relation does not exist"}
    )
    adapter = _adapter(runner)
    res = adapter.run_drill("inst", "/x")
    assert res.success is False
    assert res.row_count is None
    assert res.validation_table == "cases"
    assert "psql count failed" in (res.error or "")
    assert "relation does not exist" in (res.error or "")


def test_run_drill_returns_failure_when_createdb_fails() -> None:
    runner = FakeSubprocessRunner(
        returncodes={"createdb": 1}, stderrs={"createdb": "permission denied"}
    )
    adapter = _adapter(runner)
    res = adapter.run_drill("inst", "/x")
    assert res.success is False
    assert "createdb failed" in (res.error or "")
    assert "pg_restore" not in runner.commands_invoked()


def test_run_drill_drops_drill_db_after_success_best_effort() -> None:
    runner = FakeSubprocessRunner(stdouts={"psql": "5\n"})
    adapter = _adapter(runner)
    res = adapter.run_drill("inst", "/x")
    assert res.success is True
    assert "dropdb" in runner.commands_invoked()
    dropdb_call = next(c for c in runner.calls if c[0] == "dropdb")
    assert "--if-exists" in dropdb_call


def test_run_drill_drops_drill_db_after_failure_best_effort() -> None:
    runner = FakeSubprocessRunner(returncodes={"pg_restore": 1})
    adapter = _adapter(runner)
    res = adapter.run_drill("inst", "/x")
    assert res.success is False
    # Cleanup must still attempt dropdb even on the failure path
    assert "dropdb" in runner.commands_invoked()


def test_run_drill_uses_injected_clock_for_unique_db_name() -> None:
    runner = FakeSubprocessRunner(stdouts={"psql": "0\n"})
    adapter = _adapter(runner, clock_value=1700000000.0)
    adapter.run_drill("inst", "/x")
    createdb_call = next(c for c in runner.calls if c[0] == "createdb")
    db_name = createdb_call[1]
    assert db_name == "postgres-restore-drill-inst-1700000000"


def test_run_drill_honours_explicit_target_db_argument() -> None:
    runner = FakeSubprocessRunner(stdouts={"psql": "0\n"})
    adapter = _adapter(runner)
    adapter.run_drill("inst", "/x", target_db="custom-drill-db")
    createdb_call = next(c for c in runner.calls if c[0] == "createdb")
    assert createdb_call[1] == "custom-drill-db"


def test_run_drill_uses_custom_validation_table_when_overridden() -> None:
    runner = FakeSubprocessRunner(stdouts={"psql": "7\n"})
    adapter = _adapter(runner, validation_table="customers")
    res = adapter.run_drill("inst", "/x")
    psql_call = next(c for c in runner.calls if c[0] == "psql")
    assert any("SELECT count(*) FROM customers;" in arg for arg in psql_call)
    assert res.validation_table == "customers"


def test_factory_disabled_raises_restore_drill_disabled_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESTORE_DRILL_ENABLED", "false")
    get_restore_drill_adapter.cache_clear()
    try:
        with pytest.raises(RestoreDrillDisabledError):
            get_restore_drill_adapter()
    finally:
        get_restore_drill_adapter.cache_clear()


def test_factory_returns_singleton_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESTORE_DRILL_ENABLED", "true")
    get_restore_drill_adapter.cache_clear()
    try:
        a = get_restore_drill_adapter()
        b = get_restore_drill_adapter()
        assert a is b
        assert isinstance(a, LocalRestoreDrillAdapter)
    finally:
        get_restore_drill_adapter.cache_clear()


def test_run_drill_returns_failure_when_psql_stdout_unparsable() -> None:
    runner = FakeSubprocessRunner(stdouts={"psql": "not-a-number\n"})
    adapter = _adapter(runner)
    res = adapter.run_drill("inst", "/x")
    assert res.success is False
    assert "could not parse row count" in (res.error or "")


def test_run_drill_uses_config_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESTORE_DRILL_ENABLED", "true")
    monkeypatch.setenv("RESTORE_DRILL_VALIDATION_TABLE", "applicants")
    monkeypatch.setenv("RESTORE_DRILL_DB_PREFIX", "drill-")
    cfg = RestoreDrillConfig.from_env()
    assert cfg.enabled is True
    assert cfg.validation_table == "applicants"
    assert cfg.drill_db_prefix == "drill-"
