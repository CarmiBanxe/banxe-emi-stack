"""
Tests for scripts/ci-protection-drift-html-render.py — S16.12 CLI.

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

from services.ci_governance.drift_html_renderer import (
    DriftHtmlRenderer,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "ci-protection-drift-html-render.py"


def _load_script_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "_ci_drift_html_render_script",
        _SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["_ci_drift_html_render_script"] = module
    spec.loader.exec_module(module)
    return module


mod = _load_script_module()

_FIXED_CLOCK = 100_000.0


class _FakeHistoryStore:
    def read_all(self, limit: int | None = None) -> list[dict]:
        return []

    def read_since(self, since_ts: float) -> list[dict]:
        return []


def _make_renderer(file_writer=None):
    return DriftHtmlRenderer(
        history_store=_FakeHistoryStore(),
        clock=lambda: _FIXED_CLOCK,
        file_writer=file_writer,
    )


def test_script_uses_default_report_path_when_env_absent(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("CI_GOVERNANCE_HTML_REPORT_PATH", raising=False)

    captured_paths: list[str] = []

    def spy_writer(path: str, body: str) -> None:
        captured_paths.append(path)

    rend = _make_renderer(file_writer=spy_writer)
    monkeypatch.setattr(
        "services.ci_governance.factory.get_drift_html_renderer",
        lambda: rend,
    )
    rc = mod.main([])
    assert rc == 0
    assert captured_paths[0] == mod._DEFAULT_REPORT_PATH


def test_script_uses_env_path_when_present(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    custom = str(tmp_path / "custom.html")
    monkeypatch.setenv("CI_GOVERNANCE_HTML_REPORT_PATH", custom)

    captured_paths: list[str] = []

    def spy_writer(path: str, body: str) -> None:
        captured_paths.append(path)

    rend = _make_renderer(file_writer=spy_writer)
    monkeypatch.setattr(
        "services.ci_governance.factory.get_drift_html_renderer",
        lambda: rend,
    )
    rc = mod.main([])
    assert rc == 0
    assert captured_paths[0] == custom


def test_script_uses_default_window_604800_and_limit_500(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = str(tmp_path / "report.html")

    captured_args: list[tuple[int, int]] = []
    original_render = DriftHtmlRenderer.render

    def tracking_render(self, report_path, window_seconds=604800, limit=500):
        captured_args.append((window_seconds, limit))
        return original_render(self, report_path, window_seconds, limit)

    rend = _make_renderer(file_writer=lambda p, b: None)
    monkeypatch.setattr(
        "services.ci_governance.factory.get_drift_html_renderer",
        lambda: rend,
    )
    monkeypatch.setattr(DriftHtmlRenderer, "render", tracking_render)
    rc = mod.main(["--report-path", target])
    assert rc == 0
    assert captured_args[0] == (604800, 500)


def test_script_exits_0_on_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = str(tmp_path / "report.html")
    rend = _make_renderer(file_writer=lambda p, b: None)
    monkeypatch.setattr(
        "services.ci_governance.factory.get_drift_html_renderer",
        lambda: rend,
    )
    rc = mod.main(["--report-path", target])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["success"] is True
