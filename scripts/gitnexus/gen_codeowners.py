#!/usr/bin/env python3
"""gen_codeowners.py — generate .github/CODEOWNERS from config/gitnexus/ownership.map.json.

STEP2 of the Fable 5 rollout (docs/canon/GITNEXUS-STEP2-CODEOWNERS.md). Single source
of truth is the JSON map; CODEOWNERS is a build artifact — never hand-edit both.
Deterministic output (zone order = map order), stdlib-only, no network.

Usage:
    python3 scripts/gitnexus/gen_codeowners.py            # (re)write .github/CODEOWNERS
    python3 scripts/gitnexus/gen_codeowners.py --check    # exit 1 on drift (CI mode)

Exit codes: 0 OK · 1 drift detected (--check) or write failure.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
MAP_PATH = REPO_ROOT / "config" / "gitnexus" / "ownership.map.json"
OUT_PATH = REPO_ROOT / ".github" / "CODEOWNERS"

HEADER = """\
# CODEOWNERS — banxe-emi-stack  [GENERATED — DO NOT HAND-EDIT]
# Source of truth: config/gitnexus/ownership.map.json
# Regenerate:      python3 scripts/gitnexus/gen_codeowners.py
# Drift check:     python3 scripts/gitnexus/gen_codeowners.py --check  (CI: codeowners-coverage)
# Canon:           docs/canon/GITNEXUS-STEP2-CODEOWNERS.md (STEP2, Fable 5 rollout)
#
# USER-OWNED repo: only collaborators with write access are enforceable owners.
# Role names below are OPERATOR-BINDING-REQUIRED placeholders (comments only) —
# bind to real teams and regenerate when the GitHub org exists.
# Syntax: .gitignore-style patterns; LAST matching pattern wins.
"""


def owners_str(github_logins: list[str]) -> str:
    """Render a list of GitHub logins as a CODEOWNERS owner field."""
    return " ".join(f"@{login}" for login in github_logins)


def render(data: dict) -> str:
    """Render the full CODEOWNERS text from the ownership map (deterministic)."""
    default = data["default_owner"]
    lines: list[str] = [HEADER]
    lines.append(
        f"# freshness: generated_at={data['freshness']['generated_at']} "
        f"review_by={data['freshness']['review_by']}"
    )
    lines.append("")
    lines.append(f"# default — role: {default['role']}")
    lines.append(f"*\t{owners_str(default['github'])}")
    for zone in data["zones"]:
        lines.append("")
        lines.append(f"# zone: {zone['zone']} [{zone['criticality']}] — role: {zone['role']}")
        owners = owners_str(zone.get("github", default["github"]))
        for pattern in zone["patterns"]:
            lines.append(f"{pattern}\t{owners}")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    """Generate CODEOWNERS, or verify it matches the map in --check mode."""
    data = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    rendered = render(data)
    if "--check" in argv:
        current = OUT_PATH.read_text(encoding="utf-8") if OUT_PATH.exists() else ""
        if current != rendered:
            sys.stderr.write(
                "DRIFT: .github/CODEOWNERS does not match config/gitnexus/ownership.map.json.\n"
                "Regenerate: python3 scripts/gitnexus/gen_codeowners.py\n"
            )
            return 1
        print("codeowners drift check OK (CODEOWNERS matches ownership.map.json)")
        return 0
    OUT_PATH.write_text(rendered, encoding="utf-8")
    print(f"wrote {OUT_PATH.relative_to(REPO_ROOT)} ({len(rendered.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
