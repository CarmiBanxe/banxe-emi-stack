#!/usr/bin/env python3
"""
ci-protection-drift-check.py — S16.6 CI governance drift sentry CLI.

Compares the live branch-protection state on `main` against the S16.5
baseline (`.github/protection-update-v2.json` by default) and reports any
drift. Read-only: never mutates remote state.

Modes
-----
- `--dry-run-payload <path>` : load the payload from a JSON file (operator
  captured it earlier via `gh api .../branches/main/protection`). Pure
  offline — no network access.
- (default)                  : real GitHub-API reader. **NOT WIRED YET** in
  S16.6. CLI prints the diagnostic and exits 2 (cron-safe). Wiring requires
  GH_TOKEN / PAT plumbing and lands in a follow-up step.

Flags
-----
- `--baseline <path>`        : override the baseline path (default:
                                `.github/protection-update-v2.json`).
- `--emit-alert`             : when drift is detected, route an alert via
                                the ADR-033 AlertRoutingPort. Off by
                                default (cron-safe dry runs).

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
        "(offline mode; bypasses the real-API reader)",
    )
    p.add_argument(
        "--emit-alert",
        action="store_true",
        help="route a drift alert via the ADR-033 AlertRoutingPort on drift",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    # Resolve the reader.
    if args.dry_run_payload:
        from services.ci_governance.in_memory_protection_reader import (
            InMemoryProtectionReader,
        )

        payload_text = Path(args.dry_run_payload).read_text(encoding="utf-8")
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError as exc:
            logger.error("dry-run-payload not valid JSON: %s", exc)
            return 2
        reader = InMemoryProtectionReader(payload)
    else:
        logger.error(
            "real-API reader not wired yet (S16.6 deferred to follow-up); "
            "re-invoke with --dry-run-payload <captured-gh-api.json>"
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
