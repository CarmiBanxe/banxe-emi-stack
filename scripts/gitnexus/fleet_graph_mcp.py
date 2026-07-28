#!/usr/bin/env python3
"""fleet_graph_mcp.py — READ-ONLY fleet-graph MCP server (PASS B / STEP7).

Fable 5 rollout (docs/canon/GITNEXUS-STEP7-8-MCP-MERGEQUEUE.md). Serves the
STEP4 fleet-graph DB artifact + STEP2 ownership map as MCP tools for agents.

READ-ONLY BY CONSTRUCTION (ADR-117):
  * the SQLite DB is opened with `mode=ro` at the driver level — a write attempt
    raises OperationalError (proven by unit test);
  * NO write tools are registered — every tool is a pure read;
  * NO filesystem access outside the DB artifact + the two committed maps;
  * NO cross-repo working-tree reads — cross-repo answers are DERIVED METADATA
    only (zone / room / owner_line from the crosslink table baked at build time).

NO-MOCK / freshness: every response carries graph_commit + built_at from the DB
meta table. Missing/unreadable DB or a target with status != OK => an UNKNOWN
object with a reason — never an empty result pretending to be "no impact".

Run (operator-applied, see config/gitnexus/mcp.fleet-graph.template.json):
    FLEET_GRAPH_DB=/path/to/fleet.db python3 scripts/gitnexus/fleet_graph_mcp.py

This is a governance MCP server (repo-root pinned), deliberately separate from
the product server banxe_mcp/server.py (rule 70-mcp-tools) — it serves derived
graph metadata, not banking APIs.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import sys

from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).resolve().parent))
from impact_gate import load_zones, zone_of  # noqa: E402  (sibling module, no package)

REPO_ROOT = Path(__file__).resolve().parents[2]
MAP_PATH = REPO_ROOT / "config" / "gitnexus" / "ownership.map.json"

mcp = FastMCP("fleet-graph")  # read-only server — no write tools exist below


def _db_path() -> Path:
    return Path(os.environ.get("FLEET_GRAPH_DB", str(REPO_ROOT / "fleet.db")))


def _unknown(reason: str) -> dict:
    return {
        "status": "UNKNOWN",
        "reason": reason,
        "graph_commit": "UNKNOWN",
        "built_at": "UNKNOWN",
    }


def _connect() -> sqlite3.Connection:
    """Open the fleet DB strictly read-only (mode=ro at the sqlite driver)."""
    db = _db_path()
    if not db.is_file():
        raise FileNotFoundError(f"fleet-graph DB missing: {db}")
    return sqlite3.connect(f"file:{db}?mode=ro", uri=True)


def _freshness(con: sqlite3.Connection) -> dict:
    meta = dict(con.execute("SELECT key, value FROM meta"))
    return {
        "graph_commit": meta.get("graph_commit", "UNKNOWN"),
        "built_at": meta.get("built_at", "UNKNOWN"),
    }


def graph_freshness_impl() -> dict:
    """Freshness + per-target status of the served graph."""
    try:
        con = _connect()
    except (FileNotFoundError, sqlite3.Error) as exc:
        return _unknown(str(exc))
    try:
        fresh = _freshness(con)
        targets = [
            {"project": p, "status": s, "reason": r}
            for p, s, r in con.execute("SELECT project, status, reason FROM targets")
        ]
        return {"status": "OK", **fresh, "targets": targets}
    finally:
        con.close()


def impacted_by_impl(file: str = "", symbol: str = "") -> dict:
    """Reverse dependencies of a file's defined symbols, or of one symbol."""
    if not file and not symbol:
        return _unknown("provide file= or symbol=")
    try:
        con = _connect()
    except (FileNotFoundError, sqlite3.Error) as exc:
        return _unknown(str(exc))
    try:
        fresh = _freshness(con)
        rules, _cfg = load_zones(MAP_PATH)
        if symbol:
            rows = con.execute(
                "SELECT DISTINCT src_project, src_file, kind FROM edges WHERE dst_symbol = ?",
                (symbol,),
            ).fetchall()
        else:
            statuses = dict(con.execute("SELECT project, status FROM targets"))
            projects = [
                p
                for (p,) in con.execute(
                    "SELECT DISTINCT project FROM symbols WHERE file = ?", (file,)
                )
            ]
            if projects and any(statuses.get(p) != "OK" for p in projects):
                return _unknown(f"target(s) {projects} not OK — graph cannot answer (NO-MOCK)")
            rows = con.execute(
                """SELECT DISTINCT e.src_project, e.src_file, e.kind
                   FROM symbols s JOIN edges e ON e.dst_symbol = s.symbol
                   WHERE s.file = ? AND NOT (e.src_project = s.project AND e.src_file = s.file)""",
                (file,),
            ).fetchall()
        impacted = [
            {
                "project": p,
                "file": f,
                "via": k,
                "zone": zone_of(f, rules)[0],
                "criticality": zone_of(f, rules)[1],
            }
            for p, f, k in rows
        ]
        return {
            "status": "OK",
            **fresh,
            "query": {"file": file, "symbol": symbol},
            "impacted": impacted,
            "impacted_total": len(impacted),
        }
    finally:
        con.close()


def owners_of_impl(path: str) -> dict:
    """Zone + role owners of a repo path; cross-repo = derived metadata only."""
    rules, _cfg = load_zones(MAP_PATH)
    zone, crit = zone_of(path, rules)
    data = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    zone_row = next((z for z in data["zones"] if z["zone"] == zone), None)
    owners = (zone_row or {}).get("github", data["default_owner"]["github"])
    role = (zone_row or {}).get("role", data["default_owner"]["role"])
    crosslink: dict = {}
    try:
        con = _connect()
        row = con.execute(
            "SELECT room, owner_line FROM crosslink WHERE zone = ?", (zone,)
        ).fetchone()
        fresh = _freshness(con)
        con.close()
        if row:
            crosslink = {"room": row[0], "owner_line": row[1]}
    except (FileNotFoundError, sqlite3.Error) as exc:
        fresh = {"graph_commit": "UNKNOWN", "built_at": "UNKNOWN"}
        crosslink = {"note": f"crosslink unavailable: {exc}"}
    return {
        "status": "OK",
        **fresh,
        "path": path,
        "zone": zone,
        "criticality": crit,
        "github_owners": owners,
        "role": role,
        "crosslink_derived_metadata": crosslink,
    }


def criticality_of_impl(path: str) -> dict:
    """Criticality classification of a repo path (STEP2 zone map)."""
    rules, cfg = load_zones(MAP_PATH)
    zone, crit = zone_of(path, rules)
    thresholds = cfg.get("impact_gate", {}).get("thresholds", {})
    return {
        "status": "OK",
        "path": path,
        "zone": zone,
        "criticality": crit,
        "gate_threshold": thresholds.get(crit, "report"),
    }


@mcp.tool()
async def graph_freshness() -> str:
    """Freshness (graph_commit, built_at) + per-target OK/UNKNOWN of the fleet graph."""
    return json.dumps(graph_freshness_impl(), indent=2)


@mcp.tool()
async def impacted_by(file: str = "", symbol: str = "") -> str:
    """Reverse-dependency blast radius of a repo file or a SCIP symbol (read-only)."""
    return json.dumps(impacted_by_impl(file=file, symbol=symbol), indent=2)


@mcp.tool()
async def owners_of(path: str) -> str:
    """Zone, GitHub owners, role and derived cross-repo owner-line for a path."""
    return json.dumps(owners_of_impl(path), indent=2)


@mcp.tool()
async def criticality_of(path: str) -> str:
    """Zone criticality (LOW..CRITICAL) and impact-gate threshold for a path."""
    return json.dumps(criticality_of_impl(path), indent=2)


if __name__ == "__main__":
    mcp.run()  # stdio transport — operator-applied config, sandbox-only
