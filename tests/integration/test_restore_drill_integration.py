"""Integration tests for the restore-drill factory wiring (ADR-029 Step 4).

These verify the env-driven factory + RestoreDrillConfig contract without
ever invoking a real subprocess: each test uses monkeypatch.setenv to control
RESTORE_DRILL_* env vars and asserts the resulting adapter shape.
"""

from __future__ import annotations

import pytest

from services.backup.factory import (
    RestoreDrillConfig,
    RestoreDrillDisabledError,
    get_restore_drill_adapter,
)
from services.backup.local_restore_drill_adapter import LocalRestoreDrillAdapter


@pytest.fixture(autouse=True)
def _clear_factory_cache_and_env(monkeypatch: pytest.MonkeyPatch):
    for key in (
        "RESTORE_DRILL_ENABLED",
        "RESTORE_DRILL_VALIDATION_TABLE",
        "RESTORE_DRILL_DB_PREFIX",
    ):
        monkeypatch.delenv(key, raising=False)
    get_restore_drill_adapter.cache_clear()
    yield
    get_restore_drill_adapter.cache_clear()


def test_factory_raises_when_RESTORE_DRILL_ENABLED_false() -> None:
    # Default (no env) → disabled → raise
    with pytest.raises(RestoreDrillDisabledError):
        get_restore_drill_adapter()


def test_factory_returns_adapter_when_RESTORE_DRILL_ENABLED_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESTORE_DRILL_ENABLED", "true")
    get_restore_drill_adapter.cache_clear()
    adapter = get_restore_drill_adapter()
    assert isinstance(adapter, LocalRestoreDrillAdapter)


def test_factory_adapter_uses_validation_table_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESTORE_DRILL_ENABLED", "true")
    monkeypatch.setenv("RESTORE_DRILL_VALIDATION_TABLE", "applicants")
    get_restore_drill_adapter.cache_clear()
    adapter = get_restore_drill_adapter()
    # private attr surfaced for assertion purposes only
    assert adapter._validation_table == "applicants"  # type: ignore[attr-defined]


def test_factory_adapter_uses_db_prefix_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESTORE_DRILL_ENABLED", "true")
    monkeypatch.setenv("RESTORE_DRILL_DB_PREFIX", "drill-")
    get_restore_drill_adapter.cache_clear()
    adapter = get_restore_drill_adapter()
    assert adapter._db_prefix == "drill-"  # type: ignore[attr-defined]


def test_restore_drill_config_defaults_when_env_absent() -> None:
    """Configuration sanity: defaults align with ADR-029 §4 (table=cases)."""
    cfg = RestoreDrillConfig.from_env()
    assert cfg.enabled is False
    assert cfg.validation_table == "cases"
    assert cfg.drill_db_prefix == "postgres-restore-drill-"
