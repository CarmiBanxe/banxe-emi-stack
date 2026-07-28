#!/usr/bin/env python3
"""obs_manifest.py — pipeline observability manifest (PASS C / STEP10).

Fable 5 rollout (docs/canon/GITNEXUS-STEP9-10-CONTRACTTESTS-OBS.md). Emits a
structured, self-hosted "trace of what the pipeline saw" per CI run — the
Langfuse-shaped record WITHOUT requiring a live Langfuse/LiteLLM server:

    { run, sha, event, built_at,
      checks: [{name, status, conclusion, started_at, completed_at, duration_s}],
      totals: {checks, completed, success, failure} }

Data source: the commit's check-runs via `gh api` (available on runners).
NO-MOCK: an empty check-run list => UNKNOWN, exit 1 — a commit in CI always has
at least this very job, so empty means the query failed, not "nothing ran".

Live Langfuse-over-LiteLLM ingestion is an OPTIONAL operator follow-up behind
LANGFUSE_HOST/LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY secrets (workflow step,
skip-success when unset). This script never needs network beyond gh.

Usage:
    obs_manifest.py --run --sha SHA --repo OWNER/REPO [--out FILE]
    obs_manifest.py --check          # self-test on canned check-runs

stdlib-only. Exit: 0 OK · 1 UNKNOWN (empty/failed collection) · 2 systemic.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys


def _duration_s(started: str | None, completed: str | None) -> float | None:
    """Duration in seconds between two ISO timestamps; None when incomplete."""
    if not started or not completed:
        return None
    try:
        t0 = dt.datetime.fromisoformat(started.replace("Z", "+00:00"))
        t1 = dt.datetime.fromisoformat(completed.replace("Z", "+00:00"))
    except ValueError:
        return None
    return round((t1 - t0).total_seconds(), 1)


def build_manifest(check_runs: list[dict], *, sha: str, run_id: str, event: str) -> dict | None:
    """Pure builder: check-runs JSON -> manifest dict. None => UNKNOWN (empty)."""
    if not check_runs:
        return None  # NO-MOCK: this job itself is a check-run — empty = collection failure
    checks = []
    for cr in check_runs:
        checks.append(
            {
                "name": cr.get("name", ""),
                "status": cr.get("status", ""),
                "conclusion": cr.get("conclusion"),
                "started_at": cr.get("started_at"),
                "completed_at": cr.get("completed_at"),
                "duration_s": _duration_s(cr.get("started_at"), cr.get("completed_at")),
            }
        )
    checks.sort(key=lambda c: c["name"])
    completed = [c for c in checks if c["status"] == "completed"]
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "sha": sha,
        "event": event,
        "built_at": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "checks": checks,
        "totals": {
            "checks": len(checks),
            "completed": len(completed),
            "success": sum(1 for c in completed if c["conclusion"] == "success"),
            "failure": sum(1 for c in completed if c["conclusion"] == "failure"),
        },
    }


def fetch_check_runs(repo: str, sha: str) -> list[dict]:
    """Collect the commit's check-runs via gh api (paginated)."""
    proc = subprocess.run(
        [
            "gh",
            "api",
            f"repos/{repo}/commits/{sha}/check-runs",
            "--paginate",
            "--jq",
            ".check_runs[]",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return []
    runs: list[dict] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line:
            runs.append(json.loads(line))
    return runs


def run(repo: str, sha: str, out: Path | None) -> int:
    """Collect, build, emit; UNKNOWN visible on empty collection."""
    check_runs = fetch_check_runs(repo, sha)
    manifest = build_manifest(
        check_runs,
        sha=sha,
        run_id=os.environ.get("GITHUB_RUN_ID", "local"),
        event=os.environ.get("GITHUB_EVENT_NAME", "local"),
    )
    if manifest is None:
        print(
            "::error title=obs-manifest UNKNOWN::empty check-run list — this job itself "
            "is a check-run, so empty means collection failed (NO-MOCK), never 'nothing ran'.",
            file=sys.stderr,
        )
        return 1
    text = json.dumps(manifest, indent=2) + "\n"
    print(text)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text)
    return 0


def self_check() -> int:
    """Self-test the pure builder on canned data (no gh, no network)."""
    canned: list[dict] = [
        {
            "name": "Ruff lint + format",
            "status": "completed",
            "conclusion": "success",
            "started_at": "2026-07-28T12:00:00Z",
            "completed_at": "2026-07-28T12:01:30Z",
        },
        {
            "name": "scip-index",
            "status": "in_progress",
            "conclusion": None,
            "started_at": "2026-07-28T12:00:10Z",
            "completed_at": None,
        },
    ]
    m = build_manifest(canned, sha="deadbeef", run_id="1", event="pull_request")
    assert m is not None
    assert m["totals"] == {"checks": 2, "completed": 1, "success": 1, "failure": 0}
    assert m["checks"][0]["duration_s"] == 90.0  # sorted: Ruff first
    assert m["checks"][1]["duration_s"] is None
    assert build_manifest([], sha="x", run_id="1", event="e") is None  # NO-MOCK
    print("obs_manifest self-check OK (builder + durations + empty=UNKNOWN)")
    return 0


def main(argv: list[str]) -> int:
    """CLI entry — see module docstring."""
    parser = argparse.ArgumentParser(description="PASS C STEP10 observability manifest")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--sha", default=os.environ.get("GITHUB_SHA", ""))
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    if args.check:
        return self_check()
    if args.run:
        if not (args.repo and args.sha):
            parser.error("--repo and --sha (or GITHUB_* env) required for --run")
        return run(args.repo, args.sha, args.out)
    parser.error("one of --check / --run is required")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
