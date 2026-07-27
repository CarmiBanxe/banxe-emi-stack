#!/usr/bin/env python3
"""impact_gate.py — reverse-dependency impact gate over the fleet graph (STEP4).

Fable 5 rollout STEP4 (docs/canon/GITNEXUS-STEP4-FLEET-GRAPH.md). For the files
changed in a PR: resolve the symbols they define (fleet.db, built by
build_fleet_graph.py), compute reverse dependencies (who references those
symbols), map both sides to STEP2 ownership zones, and emit a verdict:

    REPORT        — impact contained in the same zone, nothing critical
    ACK_REQUIRED  — blast radius crosses a zone boundary OR touches a CRITICAL
                    zone (per ownership.map.json fleet_graph.impact_gate
                    thresholds) — requires the `cross-repo-ack` label
    UNKNOWN       — the graph cannot answer (changed file's target UNKNOWN /
                    stale / missing) — fail-closed-VISIBLE, never empty-safe

NO-MOCK: UNKNOWN is a first-class verdict with reasons; blind spots (any non-OK
target) are always listed even when the verdict is computable. Freshness: the
verdict always carries graph_commit + built_at from the DB meta table.

ADVISORY in STEP4: exit 0 for every verdict unless --enforce is passed
(STEP4c/STEP8 turn enforcement on; I-27 — the gate proposes, humans decide).

Usage:
    impact_gate.py --db fleet.db --changed-files FILE [--json OUT] [--enforce] [--ack]
    impact_gate.py --self-test

stdlib + sqlite3 only, deterministic. Exit: 0 · 1 (--enforce + ACK_REQUIRED
without --ack, or --enforce + UNKNOWN) · 2 systemic (db unreadable).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys
import tempfile

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MAP = REPO_ROOT / "config" / "gitnexus" / "ownership.map.json"
DEFAULT_TARGETS = REPO_ROOT / "config" / "gitnexus" / "scip.targets.json"


def load_zones(map_path: Path) -> tuple[list[tuple[str, str, str]], dict]:
    """Return ([(pattern, zone, criticality)...] longest-first, fleet_graph cfg)."""
    data = json.loads(map_path.read_text(encoding="utf-8"))
    rules: list[tuple[str, str, str]] = []
    for zone in data["zones"]:
        for pattern in zone["patterns"]:
            rules.append((pattern.strip("/"), zone["zone"], zone["criticality"]))
    rules.sort(key=lambda r: len(r[0]), reverse=True)
    return rules, data.get("fleet_graph", {})


def zone_of(path: str, rules: list[tuple[str, str, str]]) -> tuple[str, str]:
    """Map a repo path to (zone, criticality); unmatched -> ('other', 'MEDIUM')."""
    for prefix, zone, crit in rules:
        if path == prefix or path.startswith(prefix.rstrip("/") + "/") or prefix in ("",):
            return zone, crit
    return "other", "MEDIUM"


def project_of(path: str, targets: list[dict]) -> str | None:
    """Longest-prefix target match; root python target catches remaining .py files."""
    best: tuple[int, str] | None = None
    for t in targets:
        tpath, slug = t["path"], t["slug"]
        if tpath == ".":
            if path.endswith(".py") and (best is None or best[0] < 0):
                best = (-1, f"emi-{slug}")  # weakest match — root fallback
        elif path.startswith(tpath.rstrip("/") + "/"):
            if best is None or len(tpath) > best[0]:
                best = (len(tpath), f"emi-{slug}")
    return best[1] if best else None


def run_gate(db: Path, changed: list[str], map_path: Path, targets_path: Path, ack: bool) -> dict:
    """Compute the impact verdict for a changed-file set. Pure read over fleet.db."""
    rules, cfg = load_zones(map_path)
    thresholds = cfg.get("impact_gate", {}).get(
        "thresholds", {"CRITICAL": "ack-required", "HIGH": "warn"}
    )
    targets = json.loads(targets_path.read_text(encoding="utf-8"))["targets"]
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    meta = dict(con.execute("SELECT key, value FROM meta"))
    statuses = {p: (s, r) for p, s, r in con.execute("SELECT project, status, reason FROM targets")}
    blind_spots = [
        {"project": p, "status": s, "reason": r}
        for p, (s, r) in sorted(statuses.items())
        if s != "OK"
    ]

    impacted: list[dict] = []
    unknown_reasons: list[str] = []
    changed_zones: set[str] = set()
    max_crit = "LOW"
    order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}

    for path in changed:
        zone, crit = zone_of(path, rules)
        changed_zones.add(zone)
        if order[crit] > order[max_crit]:
            max_crit = crit
        project = project_of(path, targets)
        if project is None:
            continue  # non-code file — structural zone info only
        status, reason = statuses.get(project, ("UNKNOWN", "project not in graph"))
        if status != "OK":
            unknown_reasons.append(f"{path}: target {project} is {status} ({reason})")
            continue
        rows = con.execute(
            """SELECT DISTINCT e.src_project, e.src_file, e.kind
               FROM symbols s JOIN edges e ON e.dst_symbol = s.symbol
               WHERE s.project = ? AND s.file = ?
                 AND NOT (e.src_project = s.project AND e.src_file = s.file)""",
            (project, path),  # builder stores repo-relative paths — direct match
        ).fetchall()
        for src_project, src_file, kind in rows:
            izone, icrit = zone_of(src_file, rules)
            if order[icrit] > order[max_crit]:
                max_crit = icrit
            impacted.append(
                {
                    "file": src_file,
                    "project": src_project,
                    "zone": izone,
                    "criticality": icrit,
                    "via": kind,
                    "caused_by": path,
                }
            )

    cross_zone = any(i["zone"] not in changed_zones for i in impacted)
    if unknown_reasons:
        verdict = "UNKNOWN"
    elif (thresholds.get(max_crit) == "ack-required") or cross_zone:
        verdict = "ACK_REQUIRED"
    else:
        verdict = "REPORT"

    con.close()
    return {
        "verdict": verdict,
        "ack_present": ack,
        "graph_commit": meta.get("graph_commit", "UNKNOWN"),
        "built_at": meta.get("built_at", "UNKNOWN"),
        "changed_files": len(changed),
        "changed_zones": sorted(changed_zones),
        "max_criticality": max_crit,
        "cross_zone": cross_zone,
        "impacted": impacted[:200],  # cap the report, never the computation
        "impacted_total": len(impacted),
        "unknown_reasons": unknown_reasons,
        "blind_spots": blind_spots,
    }


def self_test() -> int:
    """Synthetic DB: assert ACK_REQUIRED (cross-zone), REPORT, and UNKNOWN paths."""
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "fleet.db"
        con = sqlite3.connect(db)
        con.executescript(
            """CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
               CREATE TABLE targets(project TEXT PRIMARY KEY, path TEXT, lang TEXT,
                 status TEXT, reason TEXT, graph_commit TEXT, built_at TEXT, scip_bytes INT);
               CREATE TABLE symbols(id INTEGER PRIMARY KEY, project TEXT, symbol TEXT,
                 kind INT, file TEXT);
               CREATE TABLE edges(id INTEGER PRIMARY KEY, src_project TEXT, src_file TEXT,
                 dst_symbol TEXT, kind TEXT);"""
        )
        con.execute("INSERT INTO meta VALUES('graph_commit','deadbeef')")
        con.execute("INSERT INTO meta VALUES('built_at','2026-01-01T00:00:00Z')")
        con.execute("INSERT INTO targets VALUES('emi-root-python','.','python','OK','', 'x','y',9)")
        con.execute(
            "INSERT INTO targets VALUES('emi-frontend','frontend','typescript',"
            "'UNKNOWN','npm ci failed','x','y',0)"
        )
        con.execute(
            "INSERT INTO symbols(project,symbol,kind,file) "
            "VALUES('emi-root-python','pkg/aml/Check#',7,'services/aml/checker.py')"
        )
        con.execute(
            "INSERT INTO edges(src_project,src_file,dst_symbol,kind) "
            "VALUES('emi-root-python','services/ledger/core.py','pkg/aml/Check#','ref')"
        )
        con.commit()
        con.close()

        maps, targets = DEFAULT_MAP, DEFAULT_TARGETS
        # 1) aml change referenced from ledger zone -> cross-zone + CRITICAL -> ACK
        r1 = run_gate(db, ["services/aml/checker.py"], maps, targets, ack=False)
        assert r1["verdict"] == "ACK_REQUIRED", r1["verdict"]
        assert r1["cross_zone"] is True
        assert r1["blind_spots"], "frontend UNKNOWN must be listed as blind spot"
        # 2) docs-only change -> REPORT (no project, no edges)
        r2 = run_gate(db, ["docs/README-x.md"], maps, targets, ack=False)
        assert r2["verdict"] == "REPORT", r2["verdict"]
        # 3) change in an UNKNOWN target -> UNKNOWN, fail-closed-visible
        r3 = run_gate(db, ["frontend/src/App.tsx"], maps, targets, ack=False)
        assert r3["verdict"] == "UNKNOWN", r3["verdict"]
        assert r3["unknown_reasons"]
    print("impact_gate self-test OK (ACK_REQUIRED / REPORT / UNKNOWN paths)")
    return 0


def main(argv: list[str]) -> int:
    """CLI entry — see module docstring for semantics."""
    parser = argparse.ArgumentParser(description="STEP4 reverse-dependency impact gate")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--db", type=Path)
    parser.add_argument("--changed-files", type=Path)
    parser.add_argument("--ownership", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--targets", type=Path, default=DEFAULT_TARGETS)
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--enforce", action="store_true")
    parser.add_argument("--ack", action="store_true", help="cross-repo-ack label is present")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if not (args.db and args.changed_files):
        parser.error("--db and --changed-files are required")
    if not args.db.is_file():
        print("::error::fleet.db missing — gate cannot run (systemic)", file=sys.stderr)
        return 2
    changed = [
        line.strip()
        for line in args.changed_files.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    result = run_gate(args.db, changed, args.ownership, args.targets, args.ack)
    print(json.dumps(result, indent=2))
    if args.json:
        args.json.write_text(json.dumps(result, indent=2) + "\n")
    if result["verdict"] == "ACK_REQUIRED" and not args.ack:
        print(
            "::warning title=impact-gate ACK_REQUIRED::blast radius crosses zone/CRITICAL "
            "boundaries — add label 'cross-repo-ack' (advisory in STEP4).",
            file=sys.stderr,
        )
    if result["verdict"] == "UNKNOWN":
        print(
            "::warning title=impact-gate UNKNOWN::graph cannot answer for this change "
            "(see unknown_reasons) — degrade to structural review + human ack (NO-MOCK).",
            file=sys.stderr,
        )
    if args.enforce and result["verdict"] == "ACK_REQUIRED" and not args.ack:
        return 1
    if args.enforce and result["verdict"] == "UNKNOWN":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
