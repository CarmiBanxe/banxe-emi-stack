"""Tests for drift history integration in ci-protection-drift-check.py (S16.9).

Loads the hyphenated script via importlib.util (same pattern as
test_drift_check_script.py).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType
from unittest.mock import patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "ci-protection-drift-check.py"


def _load_script_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_ci_drift_script_hist", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["_ci_drift_script_hist"] = module
    spec.loader.exec_module(module)
    return module


_BASELINE_MATCH = {
    "required_status_checks": {
        "strict": True,
        "checks": [{"context": "ci/lint"}],
    },
    "enforce_admins": False,
}

_BASELINE_DRIFT = {
    "required_status_checks": {
        "strict": True,
        "checks": [{"context": "ci/lint"}, {"context": "ci/deploy"}],
    },
    "enforce_admins": True,
}

_LIVE_PAYLOAD = {
    "required_status_checks": {
        "strict": True,
        "checks": [{"context": "ci/lint", "app_id": 1}],
    },
    "enforce_admins": {"enabled": False},
}


def _write(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


class TestDriftCheckScriptHistory:
    def test_script_appends_to_history_when_flag_present(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        baseline = _write(tmp_path / "baseline.json", _BASELINE_DRIFT)
        live = _write(tmp_path / "live.json", _LIVE_PAYLOAD)
        history = tmp_path / "history.jsonl"

        rc = mod.main(
            [
                "--baseline",
                str(baseline),
                "--dry-run-payload",
                str(live),
                "--history-path",
                str(history),
            ]
        )
        assert rc == 1  # drift
        lines = [ln for ln in history.read_text().splitlines() if ln.strip()]
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["drift_detected"] is True

    def test_script_skips_history_when_no_history_flag(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        baseline = _write(tmp_path / "baseline.json", _BASELINE_DRIFT)
        live = _write(tmp_path / "live.json", _LIVE_PAYLOAD)
        history = tmp_path / "history.jsonl"

        rc = mod.main(
            [
                "--baseline",
                str(baseline),
                "--dry-run-payload",
                str(live),
                "--history-path",
                str(history),
                "--no-history",
            ]
        )
        assert rc == 1
        assert not history.exists()

    def test_script_uses_env_path_when_history_path_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mod = _load_script_module()
        baseline = _write(tmp_path / "baseline.json", _BASELINE_DRIFT)
        live = _write(tmp_path / "live.json", _LIVE_PAYLOAD)
        history = tmp_path / "env-history.jsonl"
        monkeypatch.setenv("CI_GOVERNANCE_DRIFT_HISTORY_PATH", str(history))

        rc = mod.main(
            [
                "--baseline",
                str(baseline),
                "--dry-run-payload",
                str(live),
            ]
        )
        assert rc == 1
        lines = [ln for ln in history.read_text().splitlines() if ln.strip()]
        assert len(lines) >= 1

    def test_script_does_not_crash_when_history_append_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        baseline = _write(tmp_path / "baseline.json", _BASELINE_DRIFT)
        live = _write(tmp_path / "live.json", _LIVE_PAYLOAD)

        with patch(
            "services.ci_governance.drift_history_store.DriftHistoryStore.append_result",
            side_effect=RuntimeError("BrokenStore"),
        ):
            rc = mod.main(
                [
                    "--baseline",
                    str(baseline),
                    "--dry-run-payload",
                    str(live),
                    "--history-path",
                    "/nonexistent/path/h.jsonl",
                ]
            )
            assert rc == 1  # drift detected, no crash
