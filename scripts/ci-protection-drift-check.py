#!/usr/bin/env python3
"""
ci-protection-drift-check.py — CI governance drift sentry CLI
(S16.6 baseline + S16.7 real-API reader).

Compares the live branch-protection state on `main` against the S16.5
baseline (`.github/protection-update-v2.json` by default) and reports any
drift. Read-only: never mutates remote state.

Modes
-----
- `--dry-run-payload <path>` : load the payload from a JSON file (operator
  captured it earlier via `gh api .../branches/main/protection`). Pure
  offline — no network access.
- (default)                  : real GitHub-API reader if any of
  CI_GOVERNANCE_GH_TOKEN / GH_TOKEN / GITHUB_TOKEN env vars is set.
  Otherwise exits 2 (cron-safe). Real adapter is read-only —
  GET /repos/{owner}/{repo}/branches/{branch}/protection — no mutation.

Flags
-----
- `--baseline <path>`        : override the baseline path (default:
                                `.github/protection-update-v2.json`).
- `--emit-alert`             : when drift is detected, route an alert via
                                the ADR-033 AlertRoutingPort. Off by
                                default (cron-safe dry runs).
- `--force-real-api`         : force the real GitHub-API reader even when
                                --dry-run-payload is supplied. Useful for
                                operator-driven validation runs that must
                                hit the live state, ignoring any local
                                payload snapshot.

Exit codes
----------
- 0 : live state matches baseline (no drift)
- 1 : drift detected
- 2 : environment misconfiguration (no reader wired and no
       --dry-run-payload supplied)
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import json
import logging
import os
from pathlib import Path
import sys

_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger("banxe.ci-protection-drift-check")


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--baseline",
        default=".github/protection-update-v2.json",
        help="path to baseline JSON (default: .github/protection-update-v2.json)",
    )
    p.add_argument(
        "--dry-run-payload",
        default=None,
        help="path to a JSON file containing a captured GitHub-API payload "
        "(offline mode; bypasses the real-API reader unless --force-real-api)",
    )
    p.add_argument(
        "--emit-alert",
        action="store_true",
        help="route a drift alert via the ADR-033 AlertRoutingPort on drift",
    )
    p.add_argument(
        "--force-real-api",
        action="store_true",
        help="force the real GitHub-API reader (overrides --dry-run-payload)",
    )
    return p


def _load_payload_reader(path: str):
    """Build an InMemoryProtectionReader from a captured JSON payload file."""
    from services.ci_governance.in_memory_protection_reader import (
        InMemoryProtectionReader,
    )

    payload_text = Path(path).read_text(encoding="utf-8")
    payload = json.loads(payload_text)
    return InMemoryProtectionReader(payload)


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    from services.ci_governance.factory import (
        get_real_gh_protection_reader,
        resolve_gh_token,
    )

    # Reader-selection precedence:
    #   1. --force-real-api  → real-API reader, ignore --dry-run-payload
    #   2. --dry-run-payload → in-memory reader from the captured JSON
    #   3. any token env present → real-API reader (auto)
    #   4. otherwise → exit 2 (cron-safe)
    if args.force_real_api:
        if resolve_gh_token() is None:
            logger.error(
                "--force-real-api set but no token env (CI_GOVERNANCE_GH_TOKEN / "
                "GH_TOKEN / GITHUB_TOKEN) is present"
            )
            return 2
        reader = get_real_gh_protection_reader()
    elif args.dry_run_payload:
        try:
            reader = _load_payload_reader(args.dry_run_payload)
        except json.JSONDecodeError as exc:
            logger.error("dry-run-payload not valid JSON: %s", exc)
            return 2
    elif resolve_gh_token() is not None:
        reader = get_real_gh_protection_reader()
    else:
        logger.error(
            "no reader wired: supply --dry-run-payload <captured-gh-api.json> "
            "OR set CI_GOVERNANCE_GH_TOKEN / GH_TOKEN / GITHUB_TOKEN in env"
        )
        return 2

    from services.ci_governance.drift_detector import DriftDetector

    detector = DriftDetector(reader=reader, baseline_path=args.baseline)
    try:
        result = detector.detect_drift()
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        return 2

    print(json.dumps(dataclasses.asdict(result), default=str))

    if not result.drift_detected:
        logger.info("ci-protection-drift-check: OK (no drift)")
        return 0

    logger.warning("ci-protection-drift-check: DRIFT DETECTED — %s", result.summary)

    if args.emit_alert:
        from services.ci_governance.factory import get_drift_alert_emitter

        with contextlib.suppress(Exception):
            get_drift_alert_emitter().emit(result)

    return 1


if __name__ == "__main__":
    sys.exit(main())
