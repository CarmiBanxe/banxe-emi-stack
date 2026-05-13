#!/usr/bin/env python3
"""
ci-protection-drift-history-query.py — Read-only CLI to query S16.9 drift history JSONL.

Operator audit-trail tool: filters and formats records from the append-only
drift-history.jsonl written by S16.9 DriftHistoryStore.  Never mutates the
history file; exit 0 on missing file (empty result).

Refs: S16.10; S16.9 (#140); S16.6 (#137).
"""

from __future__ import annotations

import argparse
import contextlib
from datetime import UTC, datetime
import json
import sys


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Query the append-only drift history JSONL (S16.9).",
    )
    p.add_argument(
        "--history-path",
        default=None,
        help=(
            "Path to drift-history.jsonl. "
            "Default: env CI_GOVERNANCE_DRIFT_HISTORY_PATH or "
            "/var/cache/banxe/drift-history.jsonl"
        ),
    )
    p.add_argument(
        "--since-ts",
        type=float,
        default=None,
        help="Unix timestamp lower bound (inclusive). Default: 0 = all.",
    )
    p.add_argument(
        "--since-iso",
        type=str,
        default=None,
        help="ISO-8601 lower bound (alternative to --since-ts).",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Max records to return. 0 = unlimited. Default: 100.",
    )
    p.add_argument(
        "--only-drift",
        action="store_true",
        help="Show only records where drift_detected=true.",
    )
    p.add_argument(
        "--only-critical",
        action="store_true",
        help="Show only records where strict_weakened=true.",
    )
    p.add_argument(
        "--format",
        choices=("json", "summary"),
        default="summary",
        dest="output_format",
        help="Output format. Default: summary.",
    )
    p.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output (only with --format json).",
    )
    return p


def _parse_since(args: argparse.Namespace) -> float:
    if args.since_ts is not None and args.since_iso is not None:
        raise ValueError("--since-ts and --since-iso are mutually exclusive")
    if args.since_iso is not None:
        dt = datetime.fromisoformat(args.since_iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.timestamp()
    if args.since_ts is not None:
        return args.since_ts
    return 0.0


def _resolve_store(history_path: str | None):
    """Resolve DriftHistoryStore; return None if resolution fails."""
    with contextlib.suppress(Exception):
        from services.ci_governance.drift_history_store import DriftHistoryStore
        from services.ci_governance.factory import get_drift_history_store

        if history_path is not None:
            import time

            return DriftHistoryStore(
                history_path=history_path,
                clock=time.time,
            )
        return get_drift_history_store()
    # Fallback: build store directly without factory
    with contextlib.suppress(Exception):
        import os
        import time

        from services.ci_governance.drift_history_store import DriftHistoryStore

        path = history_path or os.environ.get(
            "CI_GOVERNANCE_DRIFT_HISTORY_PATH",
            "/var/cache/banxe/drift-history.jsonl",
        )
        return DriftHistoryStore(history_path=path, clock=time.time)
    return None


def _apply_filters(
    entries: list[dict],
    *,
    only_drift: bool,
    only_critical: bool,
) -> list[dict]:
    result = entries
    if only_drift:
        result = [e for e in result if e.get("drift_detected") is True]
    if only_critical:
        result = [e for e in result if e.get("strict_weakened") is True]
    return result


def _format_summary_line(entry: dict) -> str:
    ts = entry.get("ts", 0)
    iso = datetime.fromtimestamp(ts, tz=UTC).isoformat()
    drift = entry.get("drift_detected", False)
    missing = len(entry.get("missing_rules", []))
    extra = len(entry.get("extra_rules", []))
    strict = entry.get("strict_weakened", False)
    summary = entry.get("summary", "")
    if len(summary) > 80:
        summary = summary[:77] + "..."
    return (
        f"{iso}  drift={drift}  missing={missing}  extra={extra}"
        f"  strict_weakened={strict}  {summary}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    since_ts = _parse_since(args)

    store = _resolve_store(args.history_path)
    if store is None:
        # Cannot resolve store — output empty result
        if args.output_format == "json":
            print("[]")
        return 0

    limit = args.limit if args.limit != 0 else None

    if since_ts > 0:
        entries = store.read_since(since_ts)
        if limit is not None:
            entries = entries[:limit]
    else:
        entries = store.read_all(limit=limit)

    entries = _apply_filters(
        entries,
        only_drift=args.only_drift,
        only_critical=args.only_critical,
    )

    if args.output_format == "json":
        indent = 2 if args.pretty else None
        print(json.dumps(entries, default=str, indent=indent))
    else:
        for entry in entries:
            print(_format_summary_line(entry))

    return 0


if __name__ == "__main__":
    sys.exit(main())
