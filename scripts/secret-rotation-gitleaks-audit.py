#!/usr/bin/env python3
"""
secret-rotation-gitleaks-audit.py — ADR-032 Step 5 coverage audit.

Verifies that .gitleaks.toml contains at least one rule whose regex would
match the canonical env-var form of each secret type listed in ADR-032
§Cadence-and-ownership matrix. Designed for CI use as a coverage gate.

Pure read of .gitleaks.toml (tomllib). No modification.

Exit codes:
  0  all matrix entries are covered
  1  one or more matrix entries are uncovered (full list printed)

Usage:
    python3 scripts/secret-rotation-gitleaks-audit.py
    python3 scripts/secret-rotation-gitleaks-audit.py --config path/to/.gitleaks.toml

Refs: ADR-032 §Implementation-Plan item 4 (Gitleaks enforcement).
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys
import tomllib

# ── ADR-032 §Cadence-and-ownership matrix — single source of truth ───────────
# Each entry below is one canonical env-var name used to verify gitleaks
# rule coverage. Glob entries are represented by one example name; the
# corresponding rule regex must match the glob shape.
ADR_032_MATRIX_SECRET_NAMES: list[str] = [
    "KC_CLIENT_SECRET_BANXE_COMPLIANCE_API",  # KC_CLIENT_SECRET_* (×4)
    "KC_BOOT_ADMIN_PASSWORD",
    "KC_DB_PASSWORD",
    "AUTH_SECRET_KEY",
    "POSTGRES_PASSWORD",
    "CLICKHOUSE_PASSWORD",
    "GITHUB_PAT_RELEASE_BOT",  # GitHub Actions PATs (named GITHUB_PAT_*)
    "MARBLE_API_KEY",
    "JUBE_PASSWORD",
    "SUMSUB_APP_TOKEN",
    "SUMSUB_WEBHOOK_SECRET",
    "TELEGRAM_BOT_TOKEN",
    "FCA_REGDATA_PASSWORD",
]


def _secret_env_sample(secret_name: str) -> str:
    """A representative env-var line gitleaks would scan for this secret."""
    return f"{secret_name}=AbCd1234efghIJKLmnopQRSTuvwx9012yz"


def load_rules(config_path: Path) -> list[dict]:
    """Parse .gitleaks.toml and return its [[rules]] list (empty if missing)."""
    if not config_path.exists():
        return []
    data = tomllib.loads(config_path.read_text())
    rules = data.get("rules", [])
    if not isinstance(rules, list):
        return []
    return rules


def is_covered(secret_name: str, rules: list[dict]) -> bool:
    """True iff at least one rule's regex matches the env-var sample."""
    sample = _secret_env_sample(secret_name)
    for rule in rules:
        regex = rule.get("regex")
        if not regex:
            continue
        try:
            if re.search(regex, sample):
                return True
        except re.error:
            continue
    return False


def audit(config_path: Path) -> tuple[int, list[tuple[str, bool]]]:
    """Run the audit. Returns (exit_code, [(name, covered_bool), ...])."""
    rules = load_rules(config_path)
    report = [(name, is_covered(name, rules)) for name in ADR_032_MATRIX_SECRET_NAMES]
    missing = [name for name, ok in report if not ok]
    return (0 if not missing else 1, report)


def _print_report(report: list[tuple[str, bool]]) -> None:
    print(f"ADR-032 gitleaks coverage audit — {len(report)} matrix entries")
    print("-" * 60)
    for name, ok in report:
        mark = "OK " if ok else "MISS"
        print(f"  [{mark}] {name}")
    missing = [n for n, ok in report if not ok]
    if missing:
        print(f"\nMISSING coverage for {len(missing)} entries:")
        for name in missing:
            print(f"  - {name}")
        print("\nAdd rule patterns to .gitleaks.toml to cover these.")
    else:
        print("\nAll matrix entries are covered.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(".gitleaks.toml"),
        help="Path to gitleaks toml config (default: .gitleaks.toml)",
    )
    args = parser.parse_args(argv)
    exit_code, report = audit(args.config)
    _print_report(report)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
