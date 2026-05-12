"""Unit tests for the S16.6 CLI script `scripts/ci-protection-drift-check.py`.

The script has a hyphenated filename; we load it via importlib.util to
exercise `main()` with synthetic argv. The script writes a JSON line to
stdout on drift evaluation — we capture stdout via capsys.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "ci-protection-drift-check.py"


def _load_script_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_ci_drift_script", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["_ci_drift_script"] = module
    spec.loader.exec_module(module)
    return module


_BASELINE = {
    "required_status_checks": {
        "strict": True,
        "checks": [
            {"context": "guardian-factory"},
            {"context": "Smoke Gate (mock tier)"},
        ],
    },
    "enforce_admins": False,
    "required_pull_request_reviews": None,
    "restrictions": None,
}


def _write(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_script_exits_0_when_live_matches_baseline_via_dry_run_payload(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    baseline = _write(tmp_path / "baseline.json", _BASELINE)
    live_payload = _write(
        tmp_path / "live.json",
        {
            "required_status_checks": {
                "strict": True,
                "checks": [
                    {"context": "guardian-factory", "app_id": 1},
                    {"context": "Smoke Gate (mock tier)", "app_id": 1},
                ],
            },
            "enforce_admins": {"enabled": False},
        },
    )
    mod = _load_script_module()
    rc = mod.main(
        [
            "--baseline",
            str(baseline),
            "--dry-run-payload",
            str(live_payload),
        ]
    )
    out = capsys.readouterr().out
    result = json.loads(out.strip())
    assert rc == 0
    assert result["drift_detected"] is False


def test_script_exits_1_when_drift_detected_via_dry_run_payload(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    baseline = _write(tmp_path / "baseline.json", _BASELINE)
    # Live missing one required check.
    live_payload = _write(
        tmp_path / "live.json",
        {
            "required_status_checks": {
                "strict": True,
                "checks": [{"context": "guardian-factory", "app_id": 1}],
            },
            "enforce_admins": {"enabled": False},
        },
    )
    mod = _load_script_module()
    rc = mod.main(
        [
            "--baseline",
            str(baseline),
            "--dry-run-payload",
            str(live_payload),
        ]
    )
    out = capsys.readouterr().out
    result = json.loads(out.strip())
    assert rc == 1
    assert result["drift_detected"] is True
    assert "Smoke Gate (mock tier)" in result["missing_contexts"]


def test_script_exits_2_when_no_reader_wired_and_no_dry_run(
    tmp_path: Path,
) -> None:
    baseline = _write(tmp_path / "baseline.json", _BASELINE)
    mod = _load_script_module()
    rc = mod.main(["--baseline", str(baseline)])
    assert rc == 2
