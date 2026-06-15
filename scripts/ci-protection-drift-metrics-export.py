#!/usr/bin/env python3
"""
ci-protection-drift-metrics-export.py — CLI for cron-driven Prometheus textfile export (S16.11).

Reads the S16.9 drift-history JSONL and writes a .prom file that
node_exporter --collector.textfile.directory can scrape. No HTTP server,
no push gateway, no new dependency.

Exit codes:
  0 : export succeeded (or no history — empty metrics emitted)
  1 : write failure

Refs: S16.11; S16.9 (#140); S16.6 (#137).
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys

_DEFAULT_TEXTFILE_PATH = "/var/lib/node_exporter/textfile_collector/banxe_ci_drift.prom"


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Export drift history metrics as Prometheus textfile (S16.11).",
    )
    p.add_argument(
        "--textfile-path",
        default=None,
        help=(
            "Path to write .prom file. "
            "Default: env CI_GOVERNANCE_METRICS_TEXTFILE_PATH or "
            f"{_DEFAULT_TEXTFILE_PATH}"
        ),
    )
    p.add_argument(
        "--window-seconds",
        type=int,
        default=86400,
        help="History window in seconds. Default: 86400 (24h).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    textfile_path = args.textfile_path or os.environ.get(
        "CI_GOVERNANCE_METRICS_TEXTFILE_PATH",
        _DEFAULT_TEXTFILE_PATH,
    )

    from services.ci_governance.factory import get_drift_metrics_exporter

    exporter = get_drift_metrics_exporter()
    result = exporter.export(
        textfile_path=textfile_path,
        window_seconds=args.window_seconds,
    )

    print(json.dumps(dataclasses.asdict(result), default=str))
    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
