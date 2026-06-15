"""
Tests for scripts/ci-protection-drift-metrics-export.py — S16.11 CLI.

The script has a hyphenated filename; we load it via importlib.util.
All tests are deterministic: monkeypatched factory, tmp_path, no network.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest

from services.ci_governance.drift_metrics_exporter import (
    DriftMetricsExporter,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "ci-protection-drift-metrics-export.py"


def _load_script_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "_ci_drift_metrics_export_script",
        _SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["_ci_drift_metrics_export_script"] = module
    spec.loader.exec_module(module)
    return module


mod = _load_script_module()

_FIXED_CLOCK = 100_000.0


# ---------------------------------------------------------------------------
# FakeHistoryStore for deterministic exporter
# ---------------------------------------------------------------------------


class _FakeHistoryStore:
    def read_all(self, limit: int | None = None) -> list[dict]:
        return []

    def read_since(self, since_ts: float) -> list[dict]:
        return []


def _make_exporter(file_writer=None):
    return DriftMetricsExporter(
        history_store=_FakeHistoryStore(),
        clock=lambda: _FIXED_CLOCK,
        file_writer=file_writer,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_script_uses_default_textfile_path_when_env_absent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("CI_GOVERNANCE_METRICS_TEXTFILE_PATH", raising=False)

    captured_paths: list[str] = []

    def spy_writer(path: str, body: str) -> None:
        captured_paths.append(path)

    exp = _make_exporter(file_writer=spy_writer)
    monkeypatch.setattr(
        "services.ci_governance.factory.get_drift_metrics_exporter",
        lambda: exp,
    )
    rc = mod.main([])
    assert rc == 0
    assert captured_paths[0] == mod._DEFAULT_TEXTFILE_PATH


def test_script_uses_env_path_when_present(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    custom = str(tmp_path / "custom.prom")
    monkeypatch.setenv("CI_GOVERNANCE_METRICS_TEXTFILE_PATH", custom)

    captured_paths: list[str] = []

    def spy_writer(path: str, body: str) -> None:
        captured_paths.append(path)

    exp = _make_exporter(file_writer=spy_writer)
    monkeypatch.setattr(
        "services.ci_governance.factory.get_drift_metrics_exporter",
        lambda: exp,
    )
    rc = mod.main([])
    assert rc == 0
    assert captured_paths[0] == custom


def test_script_uses_default_window_86400_when_flag_absent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = str(tmp_path / "metrics.prom")

    captured_windows: list[int] = []
    original_export = DriftMetricsExporter.export

    def tracking_export(self, textfile_path, window_seconds=86400):
        captured_windows.append(window_seconds)
        return original_export(self, textfile_path, window_seconds)

    exp = _make_exporter(file_writer=lambda p, b: None)
    monkeypatch.setattr(
        "services.ci_governance.factory.get_drift_metrics_exporter",
        lambda: exp,
    )
    monkeypatch.setattr(DriftMetricsExporter, "export", tracking_export)
    rc = mod.main(["--textfile-path", target])
    assert rc == 0
    assert captured_windows[0] == 86400


def test_script_exits_0_on_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = str(tmp_path / "metrics.prom")
    exp = _make_exporter(file_writer=lambda p, b: None)
    monkeypatch.setattr(
        "services.ci_governance.factory.get_drift_metrics_exporter",
        lambda: exp,
    )
    rc = mod.main(["--textfile-path", target])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["success"] is True
