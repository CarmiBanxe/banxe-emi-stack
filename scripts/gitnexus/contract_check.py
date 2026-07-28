#!/usr/bin/env python3
"""contract_check.py — API contract breaking-change gate (PASS A / STEP5).

Fable 5 rollout (docs/canon/GITNEXUS-STEP5-6-CONTRACTS-SBOM.md). Orchestrates:
  1. generation of the CURRENT OpenAPI spec from the FastAPI app (api.main:app),
  2. oasdiff (pinned binary, provided by CI) breaking-change diff against the
     committed baseline apps/.openapi-snapshot.json,
  3. breaking-diff of changed STATIC specs (services/payment/openapi.yml) against
     their base-revision content,
  4. a verdict: NON_BREAKING · BREAKING (fail without --ack) · UNKNOWN.

NO-MOCK: if the spec cannot be generated or oasdiff cannot run, the verdict is
UNKNOWN and the gate FAILS VISIBLY (exit 1) — it never passes silently. An
empty diff result from a failed tool is never treated as "no breaking changes".

Baseline refresh is INTENTIONAL ONLY: `--refresh-baseline` overwrites
apps/.openapi-snapshot.json locally for the operator to commit together with
the API change and the `api-breaking-ack` label. CI never auto-refreshes.

Usage:
    contract_check.py --run --oasdiff BIN [--ack] [--base-sha SHA] [--json OUT]
    contract_check.py --refresh-baseline
    contract_check.py --check          # self-test (no oasdiff needed)

stdlib-only. Exit: 0 OK/acked · 1 BREAKING-without-ack or UNKNOWN · 2 systemic.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE = REPO_ROOT / "apps" / ".openapi-snapshot.json"
STATIC_SPECS = ["services/payment/openapi.yml"]
GEN_SNIPPET = "import json; from api.main import app; print(json.dumps(app.openapi()))"


def generate_current_spec(out_path: Path) -> tuple[bool, str]:
    """Generate the live OpenAPI spec from api.main:app. False => UNKNOWN."""
    proc = subprocess.run(
        [sys.executable, "-c", GEN_SNIPPET],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )
    if proc.returncode != 0:
        return False, f"spec generation failed: {proc.stderr.strip()[-400:]}"
    try:
        spec = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return False, f"generated spec is not JSON: {exc}"
    if not spec.get("paths"):
        return False, "generated spec has no paths (empty is not safe — NO-MOCK)"
    out_path.write_text(json.dumps(spec, indent=1, sort_keys=True))
    return True, f"{len(spec['paths'])} paths"


def run_oasdiff(oasdiff: str, base: Path, head: Path) -> tuple[list[dict] | None, str]:
    """Run `oasdiff breaking base head`; None => tool-level UNKNOWN."""
    try:
        proc = subprocess.run(
            [oasdiff, "breaking", str(base), str(head), "--format", "json"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:  # binary missing/unexecutable => UNKNOWN, never a crash
        return None, f"oasdiff not runnable: {exc}"
    # oasdiff exits non-zero both on tool errors and (with --fail-on) findings;
    # we run without --fail-on so non-zero of this form means tool failure —
    # EXCEPT exit code 1 with valid JSON output (breaking changes present).
    raw = proc.stdout.strip()
    if not raw:
        if proc.returncode == 0:
            return [], ""  # explicit empty result from a successful run
        return None, f"oasdiff failed rc={proc.returncode}: {proc.stderr.strip()[-300:]}"
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None, f"oasdiff output unparsable (rc={proc.returncode})"
    return classify(payload), ""


def classify(payload: object) -> list[dict]:
    """Normalize oasdiff breaking output to a list of {id, level, text} dicts."""
    items: list[dict] = []
    raw_list: list = []
    if isinstance(payload, list):
        raw_list = payload
    elif isinstance(payload, dict):
        raw_list = payload.get("breakingChanges") or payload.get("changes") or []
    for item in raw_list:
        if isinstance(item, dict):
            items.append(
                {
                    "id": str(item.get("id", "")),
                    "level": str(item.get("level", item.get("severity", "error"))).lower(),
                    "text": str(item.get("text", item.get("description", "")))[:300],
                }
            )
    return items


def changed_static_specs(base_sha: str) -> list[str]:
    """Static contract files changed vs base (empty list when base unknown)."""
    if not base_sha:
        return []
    proc = subprocess.run(
        ["git", "diff", "--name-only", base_sha, "HEAD", "--"] + STATIC_SPECS,
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )
    return [line for line in proc.stdout.splitlines() if line.strip()]


def git_show(base_sha: str, path: str, out: Path) -> bool:
    """Materialize base-revision content of a file; False when absent at base."""
    proc = subprocess.run(
        ["git", "show", f"{base_sha}:{path}"],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )
    if proc.returncode != 0:
        return False
    out.write_text(proc.stdout)
    return True


def run(oasdiff: str, ack: bool, base_sha: str, json_out: Path | None, workdir: Path) -> int:
    """Full gate: generated spec vs baseline + changed static specs vs base."""
    result: dict = {"verdict": "NON_BREAKING", "ack_present": ack, "pairs": [], "unknown": []}

    current = workdir / "openapi-current.json"
    ok, note = generate_current_spec(current)
    if not ok:
        result["unknown"].append({"pair": "generated-vs-baseline", "reason": note})
    elif not BASELINE.is_file():
        result["unknown"].append(
            {"pair": "generated-vs-baseline", "reason": f"baseline missing: {BASELINE}"}
        )
    else:
        findings, err = run_oasdiff(oasdiff, BASELINE, current)
        if findings is None:
            result["unknown"].append({"pair": "generated-vs-baseline", "reason": err})
        else:
            result["pairs"].append(
                {"pair": "generated-vs-baseline", "note": note, "breaking": findings}
            )

    for path in changed_static_specs(base_sha):
        base_file = workdir / ("base-" + path.replace("/", "-"))
        if not git_show(base_sha, path, base_file):
            result["pairs"].append(
                {"pair": path, "note": "new file at head — no base to break", "breaking": []}
            )
            continue
        findings, err = run_oasdiff(oasdiff, base_file, REPO_ROOT / path)
        if findings is None:
            result["unknown"].append({"pair": path, "reason": err})
        else:
            result["pairs"].append({"pair": path, "note": "changed vs base", "breaking": findings})

    total_breaking = sum(len(p["breaking"]) for p in result["pairs"])
    if result["unknown"]:
        result["verdict"] = "UNKNOWN"
    elif total_breaking > 0:
        result["verdict"] = "BREAKING"
    print(json.dumps(result, indent=2))
    if json_out:
        json_out.write_text(json.dumps(result, indent=2) + "\n")

    if result["verdict"] == "UNKNOWN":
        print(
            "::error title=contract-diff UNKNOWN::spec generation or oasdiff failed — "
            "gate cannot answer; never passes silently (NO-MOCK).",
            file=sys.stderr,
        )
        return 1
    if result["verdict"] == "BREAKING" and not ack:
        print(
            f"::error title=contract-diff BREAKING::{total_breaking} breaking change(s) "
            "without label 'api-breaking-ack' — add the label after owner review "
            "(20-api-contracts.md: additive-first, /v2/ for breaking).",
            file=sys.stderr,
        )
        return 1
    if result["verdict"] == "BREAKING":
        print("::warning title=contract-diff::BREAKING acknowledged via label.", file=sys.stderr)
    return 0


def self_check() -> int:
    """Self-test without oasdiff: classifier + baseline sanity."""
    canned = {
        "breakingChanges": [
            {"id": "response-property-removed", "level": "error", "text": "removed X"},
            {"id": "optional-param-added", "level": "warn", "text": "added Y"},
        ]
    }
    items = classify(canned)
    assert len(items) == 2 and items[0]["level"] == "error", items
    assert classify([]) == []
    assert classify({"changes": [{"id": "a", "severity": "ERR", "text": "t"}]})[0]["level"] == "err"
    data = json.loads(BASELINE.read_text())
    assert data.get("openapi", "").startswith("3."), "baseline is not an OpenAPI 3 doc"
    assert len(data.get("paths", {})) > 0, "baseline has no paths"
    for spec in STATIC_SPECS:
        assert (REPO_ROOT / spec).is_file(), f"static spec missing: {spec}"
    print(
        f"contract_check self-check OK (classifier + baseline {len(data['paths'])} paths, "
        f"{len(STATIC_SPECS)} static spec(s))"
    )
    return 0


def refresh_baseline() -> int:
    """Operator-intentional baseline refresh (never run by CI)."""
    ok, note = generate_current_spec(BASELINE)
    if not ok:
        print(f"refresh failed: {note}", file=sys.stderr)
        return 2
    print(
        f"baseline refreshed: {BASELINE} ({note}). Commit it together with the API "
        "change and the 'api-breaking-ack' label — see canon refresh policy."
    )
    return 0


def main(argv: list[str]) -> int:
    """CLI entry — see module docstring."""
    parser = argparse.ArgumentParser(description="PASS A STEP5 contract gate")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--refresh-baseline", action="store_true")
    parser.add_argument("--oasdiff", default="oasdiff")
    parser.add_argument("--ack", action="store_true")
    parser.add_argument("--base-sha", default="")
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--workdir", type=Path, default=Path("/tmp"))
    args = parser.parse_args(argv)
    if args.check:
        return self_check()
    if args.refresh_baseline:
        return refresh_baseline()
    if args.run:
        args.workdir.mkdir(parents=True, exist_ok=True)
        return run(args.oasdiff, args.ack, args.base_sha, args.json, args.workdir)
    parser.error("one of --check / --run / --refresh-baseline is required")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
