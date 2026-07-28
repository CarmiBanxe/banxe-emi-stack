"""Tests for PASS C (STEP9 contract_tests + STEP10 obs_manifest).

Locks in: verdict classifier (tool crash != test failure, never trust a run
that didn't happen), UNKNOWN-on-missing behaviors (NO-MOCK), and the pure
observability-manifest builder (durations, totals, empty=UNKNOWN).
"""

from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "gitnexus"))

import contract_tests as ct  # noqa: E402
import obs_manifest as om  # noqa: E402


def test_classifier_pass_fail_unknown() -> None:
    assert ct.classify_exit(0, True) == "PASS"
    assert ct.classify_exit(1, True) == "FAIL"  # real contract violations
    assert ct.classify_exit(2, True) == "UNKNOWN"  # schemathesis tool error
    assert ct.classify_exit(137, True) == "UNKNOWN"


def test_classifier_never_trusts_a_run_that_did_not_happen() -> None:
    assert ct.classify_exit(0, False) == "UNKNOWN"  # NO-MOCK: rc=0 without a run is not PASS
    assert ct.classify_exit(-1, False) == "UNKNOWN"


def test_run_schemathesis_missing_binary_is_unknown_not_crash(tmp_path) -> None:
    schema = tmp_path / "s.json"
    schema.write_text("{}")
    rc, ran_ok, tail = ct.run_schemathesis("/nonexistent-schemathesis", schema)
    assert ran_ok is False
    assert "not runnable" in tail
    assert ct.classify_exit(rc, ran_ok) == "UNKNOWN"


def test_manifest_builder_durations_and_totals() -> None:
    canned = [
        {
            "name": "b-check",
            "status": "completed",
            "conclusion": "failure",
            "started_at": "2026-07-28T12:00:00Z",
            "completed_at": "2026-07-28T12:00:45Z",
        },
        {
            "name": "a-check",
            "status": "completed",
            "conclusion": "success",
            "started_at": "2026-07-28T12:00:00Z",
            "completed_at": "2026-07-28T12:01:30Z",
        },
        {
            "name": "c-running",
            "status": "in_progress",
            "conclusion": None,
            "started_at": "2026-07-28T12:00:10Z",
            "completed_at": None,
        },
    ]
    m = om.build_manifest(canned, sha="deadbeef", run_id="42", event="pull_request")
    assert m is not None
    assert [c["name"] for c in m["checks"]] == ["a-check", "b-check", "c-running"]  # sorted
    assert m["checks"][0]["duration_s"] == 90.0
    assert m["checks"][1]["duration_s"] == 45.0
    assert m["checks"][2]["duration_s"] is None
    assert m["totals"] == {"checks": 3, "completed": 2, "success": 1, "failure": 1}
    assert m["sha"] == "deadbeef" and m["run_id"] == "42"
    assert m["built_at"].endswith("Z")


def test_manifest_empty_is_unknown_never_empty_safe() -> None:
    # NO-MOCK: the obs job itself is a check-run — empty list = collection failure
    assert om.build_manifest([], sha="x", run_id="1", event="e") is None


def test_manifest_bad_timestamps_degrade_to_none_duration() -> None:
    canned = [
        {
            "name": "x",
            "status": "completed",
            "conclusion": "success",
            "started_at": "not-a-date",
            "completed_at": "also-not",
        }
    ]
    m = om.build_manifest(canned, sha="s", run_id="1", event="e")
    assert m is not None
    assert m["checks"][0]["duration_s"] is None


def test_self_checks_green() -> None:
    assert ct.self_check() == 0
    assert om.self_check() == 0
