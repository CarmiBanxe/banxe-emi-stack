#!/usr/bin/env python3
"""detect_impact.py — GitNexus structural impact contour for banxe-emi-stack.

PHASE1 code-contour (sandbox-scope). Ported from banxe-architecture GITNEXUS01
phase1 with one deliberate difference: this version is STRUCTURAL ONLY and NEVER
invokes an external GitNexus engine or MCP endpoint (governance + contour
bootstrap constraint — no runtime AI activation in this repo).

LICENSE DISCLAIMER: GitNexus is licensed under PolyForm-Noncommercial-1.0.0.
Sandbox/TRAINING use only without a license. PROD/commercial use requires a
purchased GitNexus license.

Behaviour (auditable, stdlib-only, read-only over git state):
  * Reads staged file paths (``git diff --staged --name-only``), or an explicit
    file list via ``--files`` (for audit/testing without staging).
  * Maps each path to a STRUCTURAL ownership category and criticality derived
    from this repo's layout (compliance-boundaries.md domains). Structure only —
    no authority/decision mapping (ADR-130/127: memory-no-authority).
  * Prints a compact impacted-directories/categories summary.
  * Fail-closed: CRITICAL paths staged without GITNEXUS_ACK=1 → exit 1.
    HIGH paths → warning only. Everything else → informational.
  * NO-MOCK: graph blast-radius is never simulated; without a live graph the
    verdict field is always risk="STRUCTURAL" (never a fake LOW/HIGH from a graph).

Exit codes: 0 OK / ack'd · 1 fail-closed (CRITICAL without GITNEXUS_ACK=1).
Python 3.12+, stdlib only. Safe to run on every commit.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import fnmatch
import os
import subprocess
import sys

DISCLAIMER: str = (
    "GitNexus license: PolyForm-Noncommercial-1.0.0. Sandbox use only without a "
    "license; PROD/commercial use requires a purchased GitNexus license."
)

# Structural ownership/criticality map for banxe-emi-stack.
# STRUCTURE ONLY (directory domains per .claude/rules/compliance-boundaries.md);
# this encodes no human authority — HITL/L4 authority stays in agent-authority.md.
# Order matters: first glob match wins.
CATEGORY_MAP: list[tuple[str, str, str]] = [
    # (glob, category, criticality)
    ("alembic/versions/*", "migrations", "CRITICAL"),
    ("services/*/migrations/*", "migrations", "CRITICAL"),
    ("services/ledger/*", "ledger-core", "CRITICAL"),
    ("services/banking-engine/*", "ledger-core", "CRITICAL"),
    ("services/payment*/*", "ledger-core", "CRITICAL"),
    ("services/aml/*", "compliance-aml", "CRITICAL"),
    ("services/kyc/*", "compliance-aml", "CRITICAL"),
    ("services/sanctions_screening/*", "compliance-aml", "CRITICAL"),
    ("services/adverse_media/*", "compliance-aml", "CRITICAL"),
    ("services/fraud/*", "compliance-aml", "CRITICAL"),
    ("services/case_management/*", "compliance-aml", "CRITICAL"),
    ("services/hitl/*", "compliance-aml", "CRITICAL"),
    ("services/recon/*", "safeguarding-recon", "CRITICAL"),
    ("services/safeguarding*/*", "safeguarding-recon", "CRITICAL"),
    ("services/statements/*", "safeguarding-recon", "CRITICAL"),
    ("services/client_statements/*", "safeguarding-recon", "CRITICAL"),
    ("services/reporting/*", "reporting-fca", "CRITICAL"),
    ("dbt/*", "reporting-fca", "CRITICAL"),
    ("services/audit_trail/*", "audit-append-only", "CRITICAL"),
    ("services/audit/*", "audit-append-only", "CRITICAL"),
    ("infra/*", "infra-governance", "HIGH"),
    ("deploy/*", "infra-governance", "HIGH"),
    (".semgrep/*", "infra-governance", "HIGH"),
    (".githooks/*", "infra-governance", "HIGH"),
    (".github/*", "infra-governance", "HIGH"),
    ("ledger/*", "infra-governance", "HIGH"),
    ("docs/canon/*", "infra-governance", "HIGH"),
    (".claude/*", "infra-governance", "HIGH"),
    ("api/*", "api-contracts", "HIGH"),
    ("services/*/contracts/*", "api-contracts", "HIGH"),
    ("services/*/api/*", "api-contracts", "HIGH"),
    ("banxe_mcp/*", "api-contracts", "HIGH"),
    ("agents/*", "agents", "HIGH"),
    ("services/*", "services-other", "MEDIUM"),
    ("frontend/*", "frontend", "MEDIUM"),
    ("scripts/*", "scripts", "MEDIUM"),
    ("tests/*", "tests", "LOW"),
    ("docs/*", "docs", "LOW"),
]

_SEVERITY_ORDER: dict[str, int] = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


def staged_files() -> list[str]:
    """Return staged file paths (empty list when nothing is staged)."""
    proc = subprocess.run(
        ["git", "diff", "--staged", "--name-only"],
        capture_output=True,
        text=True,
        check=False,
    )
    return [line for line in proc.stdout.splitlines() if line.strip()]


def classify(path: str) -> tuple[str, str]:
    """Map a repo path to (category, criticality) — first glob match wins."""
    for glob, category, crit in CATEGORY_MAP:
        if fnmatch.fnmatch(path, glob):
            return category, crit
    return "other", "MEDIUM"


def summarize(files: list[str]) -> tuple[dict[str, list[str]], str]:
    """Group files by category; return (groups, max criticality)."""
    groups: dict[str, list[str]] = defaultdict(list)
    max_crit = "LOW"
    for f in files:
        category, crit = classify(f)
        groups[f"{category} [{crit}]"].append(f)
        if _SEVERITY_ORDER[crit] > _SEVERITY_ORDER[max_crit]:
            max_crit = crit
    return dict(groups), max_crit


def main(argv: list[str] | None = None) -> int:
    """Entry point: structural impact summary + fail-closed CRITICAL gate."""
    parser = argparse.ArgumentParser(description="GitNexus structural impact (emi-stack)")
    parser.add_argument(
        "--files",
        nargs="*",
        default=None,
        help="explicit file list (default: staged files from git)",
    )
    args = parser.parse_args(argv)

    print(DISCLAIMER, file=sys.stderr)
    files = args.files if args.files is not None else staged_files()
    if not files:
        print("GitNexus impact: no staged changes — nothing to assess.")
        return 0

    groups, max_crit = summarize(files)
    dirs = sorted({os.path.dirname(f) or "." for f in files})
    print(f'GitNexus impact: risk="STRUCTURAL" files={len(files)} max_criticality={max_crit}')
    print(f"  impacted dirs: {', '.join(dirs)}")
    for label in sorted(groups):
        print(f"  {label}: {len(groups[label])} file(s)")
        for f in sorted(groups[label]):
            print(f"    - {f}")

    if max_crit == "CRITICAL":
        if os.environ.get("GITNEXUS_ACK") != "1":
            print(
                "FAIL-CLOSED: CRITICAL-path change without operator confirmation "
                "(set GITNEXUS_ACK=1 to acknowledge; enrich → impact → act).",
                file=sys.stderr,
            )
            return 1
        print("GITNEXUS_ACK=1 acknowledged — proceeding.", file=sys.stderr)
    elif max_crit == "HIGH":
        print(
            "⚠ GitNexus reminder: HIGH-criticality governance/contract paths staged "
            "(enrich → impact → act).",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
