#!/usr/bin/env python3
"""
ci-protection-drift-html-render.py — CLI for cron-driven HTML drift report (S16.12).

Reads the S16.9 drift-history JSONL and writes a static HTML5 report file
that operators can open in any browser. No server, no JS, no new dependency.

Exit codes:
  0 : render succeeded (or no history — placeholder page emitted)
  1 : write failure

Refs: S16.12; S16.9 (#140); S16.6 (#137).
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys

_DEFAULT_REPORT_PATH = "/var/cache/banxe/drift-report.html"


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Render drift history as static HTML report (S16.12).",
    )
    p.add_argument(
        "--report-path",
        default=None,
        help=(
            "Path to write HTML report. "
            "Default: env CI_GOVERNANCE_HTML_REPORT_PATH or "
            f"{_DEFAULT_REPORT_PATH}"
        ),
    )
    p.add_argument(
        "--window-seconds",
        type=int,
        default=604800,
        help="History window in seconds. Default: 604800 (7 days).",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=500,
        help="Max entries to render. Default: 500.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    report_path = args.report_path or os.environ.get(
        "CI_GOVERNANCE_HTML_REPORT_PATH",
        _DEFAULT_REPORT_PATH,
    )

    from services.ci_governance.factory import get_drift_html_renderer

    renderer = get_drift_html_renderer()
    result = renderer.render(
        report_path=report_path,
        window_seconds=args.window_seconds,
        limit=args.limit,
    )

    print(json.dumps(dataclasses.asdict(result), default=str))
    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
