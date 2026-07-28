#!/usr/bin/env python3
"""contract_tests.py — schema-driven contract tests (PASS C / STEP9).

Fable 5 rollout (docs/canon/GITNEXUS-STEP9-10-CONTRACTTESTS-OBS.md).
Orchestrates schemathesis (pinned in CI: schemathesis==3.39.16) against the
LIVE OpenAPI schema generated from api.main:app — property/contract tests
derived from the schema, run IN-PROCESS against the ASGI app (no server boot).

Tier: SMOKE — GET-only operations, 2 hypothesis examples each (bounded time on
a 463-path API). Deeper tiers (mutating methods, more examples, Pact broker
consumer contracts) are documented follow-ups, not silently skipped scope.

Verdicts:
    PASS     — schemathesis ran, no contract violations
    FAIL     — contract violations found (exit 1)
    UNKNOWN  — schema cannot be generated or schemathesis cannot run:
               FAILS VISIBLY (exit 1), never a silent pass (NO-MOCK).

Usage:
    contract_tests.py --run [--schemathesis-bin BIN] [--json OUT]
    contract_tests.py --check          # self-test, no schemathesis needed

stdlib-only orchestration. Exit: 0 PASS · 1 FAIL/UNKNOWN · 2 systemic.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from contract_check import generate_current_spec  # noqa: E402  (sibling, reuse STEP5 generator)

REPO_ROOT = Path(__file__).resolve().parents[2]
ASGI_APP = "api.main:app"
SMOKE_ARGS = [
    "--method",
    "GET",
    "--hypothesis-max-examples",
    "2",
    "--hypothesis-deadline",
    "2000",
    "--checks",
    "all",
    "--no-color",
]


def classify_exit(returncode: int, ran_ok: bool) -> str:
    """Map a schemathesis CLI exit to a verdict. Tool crash != test failure."""
    if not ran_ok:
        return "UNKNOWN"
    if returncode == 0:
        return "PASS"
    if returncode == 1:
        return "FAIL"  # contract violations found — a real red, not a tool error
    return "UNKNOWN"  # any other exit = tool-level problem, never silent pass


def run_schemathesis(bin_name: str, schema_path: Path) -> tuple[int, bool, str]:
    """Invoke schemathesis in-process ASGI mode; (rc, ran_ok, tail_of_output)."""
    cmd = [bin_name, "run", str(schema_path), f"--app={ASGI_APP}", *SMOKE_ARGS]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, check=False, cwd=REPO_ROOT, timeout=1500
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return -1, False, f"schemathesis not runnable: {exc}"
    tail = (proc.stdout + "\n" + proc.stderr)[-2000:]
    return proc.returncode, True, tail


def run(schemathesis_bin: str, json_out: Path | None, workdir: Path) -> int:
    """Generate schema, run smoke-tier contract tests, emit verdict."""
    workdir.mkdir(parents=True, exist_ok=True)
    schema_path = workdir / "openapi-current.json"
    ok, note = generate_current_spec(schema_path)
    if not ok:
        result: dict[str, object] = {
            "verdict": "UNKNOWN",
            "reason": f"schema generation failed: {note}",
        }
        print(json.dumps(result, indent=2))
        if json_out:
            json_out.write_text(json.dumps(result, indent=2) + "\n")
        print(
            "::error title=contract-tests UNKNOWN::schema cannot be generated — "
            "never a silent pass (NO-MOCK).",
            file=sys.stderr,
        )
        return 1

    rc, ran_ok, tail = run_schemathesis(schemathesis_bin, schema_path)
    verdict = classify_exit(rc, ran_ok)
    result = {
        "verdict": verdict,
        "tier": "smoke (GET-only, 2 examples/op)",
        "schema_note": note,
        "schemathesis_exit": rc,
        "output_tail": tail,
    }
    print(json.dumps({k: v for k, v in result.items() if k != "output_tail"}, indent=2))
    if json_out:
        json_out.write_text(json.dumps(result, indent=2) + "\n")
    if verdict == "UNKNOWN":
        print(
            f"::error title=contract-tests UNKNOWN::schemathesis tool-level failure "
            f"(rc={rc}) — never a silent pass (NO-MOCK). Tail:\n{tail[-600:]}",
            file=sys.stderr,
        )
        return 1
    if verdict == "FAIL":
        print(
            f"::error title=contract-tests FAIL::contract violations found. Tail:\n{tail[-600:]}",
            file=sys.stderr,
        )
        return 1
    print("contract-tests PASS (smoke tier)")
    return 0


def self_check() -> int:
    """Self-test without schemathesis: verdict classifier + generator import."""
    assert classify_exit(0, True) == "PASS"
    assert classify_exit(1, True) == "FAIL"
    assert classify_exit(2, True) == "UNKNOWN"  # tool error exit
    assert classify_exit(-1, False) == "UNKNOWN"
    assert classify_exit(0, False) == "UNKNOWN"  # never trust a run that didn't happen
    assert callable(generate_current_spec)
    print("contract_tests self-check OK (verdict classifier + STEP5 generator reuse)")
    return 0


def main(argv: list[str]) -> int:
    """CLI entry — see module docstring."""
    parser = argparse.ArgumentParser(description="PASS C STEP9 contract tests")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--schemathesis-bin", default="schemathesis")
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--workdir", type=Path, default=Path("/tmp/contract-tests"))
    args = parser.parse_args(argv)
    if args.check:
        return self_check()
    if args.run:
        return run(args.schemathesis_bin, args.json, args.workdir)
    parser.error("one of --check / --run is required")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
