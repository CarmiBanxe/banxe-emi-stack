#!/usr/bin/env python3
"""
ci-protection-snapshot-capture.py — Snapshot capture CLI (S16.8).

Captures GitHub branch-protection state on `main` into a local JSON file
that the S16.6 drift-sentry CLI can later consume via its
`--dry-run-payload <file>` path. Read-only.

Typical operator wiring:
  1. Run THIS script on a host with outbound GitHub access on a cron
     (e.g. every 30 minutes). The script writes
     /var/cache/banxe/last-protection-snapshot.json atomically.
  2. Run `scripts/ci-protection-drift-check.py --dry-run-payload
     /var/cache/banxe/last-protection-snapshot.json` on the drift-sentry
     host (which may not have outbound GitHub access).

Flags
-----
- `--snapshot-path <path>` : override the snapshot output path. Default:
                              env CI_GOVERNANCE_SNAPSHOT_PATH, falling
                              back to /var/cache/banxe/last-protection-snapshot.json.
- `--force-real-api`       : force the real GitHub-API reader regardless
                              of CI_GOVERNANCE_READER_MODE. Useful when
                              the cron host has a token but operator env
                              chose `in_memory` by mistake.
- `--pretty`               : reserved for future human-readable output;
                              JSON output is already sort-keyed +
                              indent=2 in the snapshot file.

Exit codes
----------
- 0 : capture succeeded; SnapshotResult.success == True
- 1 : capture failed (reader raised, or file_writer raised); details in
       SnapshotResult.error
- 2 : reader is in `in_memory` mode AND no token env present (cron-safe;
       the cron should not silently write a stub snapshot)
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import os
import sys

_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger("banxe.ci-protection-snapshot-capture")

_DEFAULT_SNAPSHOT_PATH = "/var/cache/banxe/last-protection-snapshot.json"


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--snapshot-path",
        default=os.environ.get("CI_GOVERNANCE_SNAPSHOT_PATH", _DEFAULT_SNAPSHOT_PATH),
        help=(
            "target file for the captured snapshot "
            "(default: env CI_GOVERNANCE_SNAPSHOT_PATH or "
            f"{_DEFAULT_SNAPSHOT_PATH})"
        ),
    )
    p.add_argument(
        "--force-real-api",
        action="store_true",
        help="force the real GitHub-API reader regardless of CI_GOVERNANCE_READER_MODE",
    )
    p.add_argument(
        "--pretty",
        action="store_true",
        help="reserved (snapshot file is already pretty-printed)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    # Reader selection guard: refuse to write a stub snapshot from the
    # in_memory reader unless the operator explicitly --force-real-api'd
    # AND has a token. This keeps the cron cron-safe — better an empty
    # SnapshotResult on stdout (exit 2) than an empty file on disk.
    from services.ci_governance.factory import (
        get_protection_reader,
        get_real_gh_protection_reader,
        get_snapshot_writer,
        resolve_gh_token,
    )
    from services.ci_governance.in_memory_protection_reader import (
        InMemoryProtectionReader,
    )
    from services.ci_governance.snapshot_writer import ProtectionSnapshotWriter

    if args.force_real_api:
        if resolve_gh_token() is None:
            logger.error(
                "--force-real-api set but no token env (CI_GOVERNANCE_GH_TOKEN / "
                "GH_TOKEN / GITHUB_TOKEN) is present"
            )
            return 2
        writer = ProtectionSnapshotWriter(reader=get_real_gh_protection_reader())
    else:
        reader = get_protection_reader()
        if isinstance(reader, InMemoryProtectionReader) and resolve_gh_token() is None:
            logger.error(
                "reader is in_memory mode and no token env present; refusing to "
                "write a stub snapshot. Set CI_GOVERNANCE_READER_MODE=gh_api (or "
                "=auto with a token) OR pass --force-real-api with a token."
            )
            return 2
        writer = get_snapshot_writer()

    result = writer.capture(args.snapshot_path)
    print(json.dumps(dataclasses.asdict(result), default=str))

    if result.success:
        logger.info("snapshot OK: %s (%s bytes)", result.snapshot_path, result.byte_size)
        return 0

    logger.error("snapshot FAIL: %s", result.error)
    # Distinguish a deliberate cron-safe stop (exit 2) from a real I/O failure (1).
    return 1


if __name__ == "__main__":
    sys.exit(main())
