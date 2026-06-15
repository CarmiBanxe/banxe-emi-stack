"""
Tests for scripts/ci-protection-drift-history-query.py — S16.10 drift history query CLI.

The script has a hyphenated filename; we load it via importlib.util.
All tests are deterministic: they use tmp_path with pre-seeded JSONL fixtures.
No network, no mutation, no side effects.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "ci-protection-drift-history-query.py"


def _load_script_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "_ci_drift_history_query_script",
        _SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["_ci_drift_history_query_script"] = module
    spec.loader.exec_module(module)
    return module


mod = _load_script_module()


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_record(
    ts: float,
    drift_detected: bool = False,
    strict_weakened: bool = False,
    missing_rules: list[str] | None = None,
    extra_rules: list[str] | None = None,
    summary: str = "",
) -> dict:
    return {
        "ts": ts,
        "drift_detected": drift_detected,
        "strict_weakened": strict_weakened,
        "missing_rules": missing_rules or [],
        "extra_rules": extra_rules or [],
        "summary": summary,
    }


_RECORDS: list[dict] = [
    _make_record(1000.0, drift_detected=False, summary="no drift at t=1000"),
    _make_record(2000.0, drift_detected=True, summary="drift at t=2000"),
    _make_record(
        3000.0,
        drift_detected=True,
        strict_weakened=True,
        missing_rules=["r1"],
        summary="critical drift at t=3000",
    ),
    _make_record(4000.0, drift_detected=False, summary="no drift at t=4000"),
    _make_record(
        5000.0,
        drift_detected=True,
        strict_weakened=True,
        missing_rules=["r2", "r3"],
        extra_rules=["x1"],
        summary="critical drift at t=5000",
    ),
]


@pytest.fixture()
def history_file(tmp_path: Path) -> Path:
    p = tmp_path / "drift-history.jsonl"
    p.write_text(
        "\n".join(json.dumps(r, separators=(",", ":")) for r in _RECORDS) + "\n",
        encoding="utf-8",
    )
    return p


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_query_returns_all_entries_when_no_filters(
    history_file: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = mod.main(["--history-path", str(history_file), "--limit", "0", "--format", "json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert len(out) == 5


def test_query_filters_by_since_ts_inclusive_lower_bound(
    history_file: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = mod.main(
        [
            "--history-path",
            str(history_file),
            "--since-ts",
            "3000",
            "--limit",
            "0",
            "--format",
            "json",
        ]
    )
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert len(out) == 3
    assert all(e["ts"] >= 3000 for e in out)


def test_query_since_iso_equivalent_to_since_ts(
    history_file: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # 3000.0 unix = 1970-01-01T00:50:00+00:00
    iso = "1970-01-01T00:50:00+00:00"
    rc = mod.main(
        [
            "--history-path",
            str(history_file),
            "--since-iso",
            iso,
            "--limit",
            "0",
            "--format",
            "json",
        ]
    )
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert len(out) == 3
    assert all(e["ts"] >= 3000 for e in out)


def test_query_since_ts_and_since_iso_together_raises_value_error(
    history_file: Path,
) -> None:
    with pytest.raises(ValueError, match="mutually exclusive"):
        mod.main(
            [
                "--history-path",
                str(history_file),
                "--since-ts",
                "1000",
                "--since-iso",
                "2020-01-01T00:00:00Z",
            ]
        )


def test_query_limit_caps_returned_records(
    history_file: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = mod.main(["--history-path", str(history_file), "--limit", "2", "--format", "json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert len(out) == 2


def test_query_limit_zero_means_unlimited(
    history_file: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = mod.main(["--history-path", str(history_file), "--limit", "0", "--format", "json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert len(out) == 5


def test_query_only_drift_filters_to_drift_detected_true(
    history_file: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = mod.main(
        ["--history-path", str(history_file), "--only-drift", "--limit", "0", "--format", "json"]
    )
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert len(out) == 3
    assert all(e["drift_detected"] is True for e in out)


def test_query_only_critical_filters_to_strict_weakened_true(
    history_file: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = mod.main(
        ["--history-path", str(history_file), "--only-critical", "--limit", "0", "--format", "json"]
    )
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert len(out) == 2
    assert all(e["strict_weakened"] is True for e in out)


def test_query_json_format_outputs_valid_json_array(
    history_file: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = mod.main(
        ["--history-path", str(history_file), "--limit", "0", "--format", "json", "--pretty"]
    )
    assert rc == 0
    raw = capsys.readouterr().out
    parsed = json.loads(raw)
    assert isinstance(parsed, list)
    assert len(parsed) == 5
    # Pretty flag means indentation present
    assert "\n " in raw


def test_query_missing_history_file_returns_empty_result_exit_zero(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing = tmp_path / "nonexistent" / "drift-history.jsonl"
    rc = mod.main(["--history-path", str(missing), "--format", "json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out == []
