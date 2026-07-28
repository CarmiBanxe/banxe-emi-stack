"""Tests for scripts/gitnexus/fleet_graph_mcp.py (PASS B / STEP7).

Locks in: READ-ONLY enforcement (driver-level mode=ro — writes raise),
UNKNOWN-on-missing-DB (NO-MOCK), freshness fields on every answer, and
derived-metadata-only cross-repo surface (crosslink table, no foreign trees).
"""

from __future__ import annotations

from pathlib import Path
import sqlite3
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "gitnexus"))

import fleet_graph_mcp as fgm  # noqa: E402

_SCHEMA = """
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE targets(project TEXT PRIMARY KEY, path TEXT, lang TEXT,
  status TEXT, reason TEXT, graph_commit TEXT, built_at TEXT, scip_bytes INT);
CREATE TABLE symbols(id INTEGER PRIMARY KEY, project TEXT, symbol TEXT, kind INT, file TEXT);
CREATE TABLE edges(id INTEGER PRIMARY KEY, src_project TEXT, src_file TEXT,
  dst_symbol TEXT, kind TEXT);
CREATE TABLE crosslink(zone TEXT PRIMARY KEY, room TEXT, owner_line TEXT);
"""


@pytest.fixture()
def fleet_db(tmp_path, monkeypatch):
    db = tmp_path / "fleet.db"
    con = sqlite3.connect(db)
    con.executescript(_SCHEMA)
    con.execute("INSERT INTO meta VALUES('graph_commit','cafebabe')")
    con.execute("INSERT INTO meta VALUES('built_at','2026-07-28T00:00:00Z')")
    con.execute("INSERT INTO targets VALUES('emi-root-python','.','python','OK','','c','b',9)")
    con.execute(
        "INSERT INTO symbols(project,symbol,kind,file) "
        "VALUES('emi-root-python','pkg/aml/Check#',7,'services/aml/checker.py')"
    )
    con.execute(
        "INSERT INTO edges(src_project,src_file,dst_symbol,kind) "
        "VALUES('emi-root-python','services/ledger/core.py','pkg/aml/Check#','ref')"
    )
    con.execute(
        "INSERT INTO crosslink VALUES('compliance-aml','F3-aml-room',"
        "'MLRO / Financial Crime (SMF17)')"
    )
    con.commit()
    con.close()
    monkeypatch.setenv("FLEET_GRAPH_DB", str(db))
    return db


def test_missing_db_returns_unknown_never_empty(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("FLEET_GRAPH_DB", str(tmp_path / "absent.db"))
    for result in (fgm.graph_freshness_impl(), fgm.impacted_by_impl(file="x.py")):
        assert result["status"] == "UNKNOWN"
        assert result["reason"]
        assert result["graph_commit"] == "UNKNOWN"  # freshness fields always present


def test_connection_is_read_only_by_construction(fleet_db) -> None:
    con = fgm._connect()
    with pytest.raises(sqlite3.OperationalError):
        con.execute("INSERT INTO meta VALUES('x','y')")
    con.close()


def test_no_write_tools_registered() -> None:
    # every public tool impl is a pure read; module exposes no mutating helper
    mutating = [
        n
        for n in dir(fgm)
        if any(v in n.lower() for v in ("write", "insert", "delete", "update", "drop"))
    ]
    assert mutating == [], mutating


def test_graph_freshness_carries_commit_and_targets(fleet_db) -> None:
    result = fgm.graph_freshness_impl()
    assert result["status"] == "OK"
    assert result["graph_commit"] == "cafebabe"
    assert result["built_at"] == "2026-07-28T00:00:00Z"
    assert result["targets"][0]["project"] == "emi-root-python"


def test_impacted_by_file_returns_cross_zone_metadata(fleet_db) -> None:
    result = fgm.impacted_by_impl(file="services/aml/checker.py")
    assert result["status"] == "OK"
    assert result["impacted_total"] == 1
    hit = result["impacted"][0]
    assert hit["file"] == "services/ledger/core.py"
    assert hit["zone"] == "ledger-core"
    assert result["graph_commit"] == "cafebabe"


def test_impacted_by_symbol(fleet_db) -> None:
    result = fgm.impacted_by_impl(symbol="pkg/aml/Check#")
    assert result["status"] == "OK"
    assert result["impacted_total"] == 1


def test_impacted_by_unknown_target_is_unknown(fleet_db) -> None:
    con = sqlite3.connect(fleet_db)
    con.execute("UPDATE targets SET status='UNKNOWN', reason='indexer failed'")
    con.commit()
    con.close()
    result = fgm.impacted_by_impl(file="services/aml/checker.py")
    assert result["status"] == "UNKNOWN"
    assert "NO-MOCK" in result["reason"]


def test_owners_of_uses_derived_crosslink_only(fleet_db) -> None:
    result = fgm.owners_of_impl("services/aml/tx_monitor.py")
    assert result["zone"] == "compliance-aml"
    assert result["criticality"] == "CRITICAL"
    assert result["github_owners"] == ["CarmiBanxe"]
    # cross-repo surface is the baked crosslink row — derived metadata, no tree read
    assert result["crosslink_derived_metadata"]["room"] == "F3-aml-room"


def test_criticality_of_threshold(fleet_db) -> None:
    result = fgm.criticality_of_impl("services/ledger/x.py")
    assert result["criticality"] == "CRITICAL"
    assert result["gate_threshold"] == "ack-required"


def test_no_args_impacted_by_is_unknown(fleet_db) -> None:
    assert fgm.impacted_by_impl()["status"] == "UNKNOWN"
