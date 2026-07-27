#!/usr/bin/env python3
"""build_fleet_graph.py — build the SQLite fleet graph from STEP3 SCIP artifacts.

Fable 5 rollout STEP4 (docs/canon/GITNEXUS-STEP4-FLEET-GRAPH.md). Parses the
`.scip` protobuf indexes produced by scip-index.yml and loads symbols + edges
into ONE SQLite database (single-writer: exactly one CI builder job, isolated
per run). stdlib + sqlite3 only — the SCIP protobuf is read with a minimal
wire-format parser for exactly the fields we need (no scip CLI, no protoc, no
new tools; Fable 5: GitNexus stays replaceable, substrate is engine-neutral).

SCIP field numbers (scip.proto, github.com/sourcegraph/scip):
    Index.documents = 2 (len-delimited, repeated)
    Document.relative_path = 1 · Document.occurrences = 2 · Document.symbols = 3
    Occurrence.range = 1 · Occurrence.symbol = 2 · Occurrence.symbol_roles = 3
    SymbolInformation.symbol = 1 · SymbolInformation.kind = 5
    SymbolRole bits: Definition=0x1, Import=0x2

NO-MOCK contract (first-class in the DB):
    * missing artifact dir           -> targets.status = UNKNOWN ("artifact missing")
    * scip-meta.json says UNKNOWN    -> carried through verbatim
    * parse failure / zero symbols   -> UNKNOWN with reason — never silently empty
    * meta table carries graph_commit + built_at (freshness is data, not vibes)

Usage:
    build_fleet_graph.py --scip-dir DIR --targets config/gitnexus/scip.targets.json \
        --out fleet.db --graph-commit SHA
    build_fleet_graph.py --check      # self-test on a synthesized SCIP index

Exit codes: 0 OK (UNKNOWNs are visible, not fatal) · 1 systemic (all targets
UNKNOWN, or self-test failure).
"""

from __future__ import annotations

import argparse
from collections.abc import Iterator
import datetime as dt
import json
from pathlib import Path
import sqlite3
import sys
import tempfile

ROLE_DEFINITION = 0x1
ROLE_IMPORT = 0x2

SCHEMA = """
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE targets(
    project TEXT PRIMARY KEY, path TEXT NOT NULL, lang TEXT NOT NULL,
    status TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '',
    graph_commit TEXT NOT NULL DEFAULT '', built_at TEXT NOT NULL DEFAULT '',
    scip_bytes INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE symbols(
    id INTEGER PRIMARY KEY, project TEXT NOT NULL, symbol TEXT NOT NULL,
    kind INTEGER NOT NULL DEFAULT 0, file TEXT NOT NULL
);
CREATE TABLE edges(
    id INTEGER PRIMARY KEY, src_project TEXT NOT NULL, src_file TEXT NOT NULL,
    dst_symbol TEXT NOT NULL, kind TEXT NOT NULL
);
CREATE TABLE crosslink(
    zone TEXT PRIMARY KEY, room TEXT, owner_line TEXT
);
CREATE INDEX idx_symbols_symbol ON symbols(symbol);
CREATE INDEX idx_symbols_loc ON symbols(project, file);
CREATE INDEX idx_edges_dst ON edges(dst_symbol);
CREATE INDEX idx_edges_src ON edges(src_project, src_file);
"""


# ── minimal protobuf wire-format reader (only what SCIP needs) ────────────────


def _read_varint(buf: bytes, i: int) -> tuple[int, int]:
    """Decode one varint at offset i; return (value, next_offset)."""
    shift = 0
    val = 0
    while True:
        byte = buf[i]
        i += 1
        val |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return val, i
        shift += 7
        if shift > 63:
            raise ValueError("varint too long")


def _iter_fields(buf: bytes) -> Iterator[tuple[int, int, bytes | int]]:
    """Yield (field_number, wire_type, value) for one protobuf message."""
    i, n = 0, len(buf)
    while i < n:
        key, i = _read_varint(buf, i)
        fno, wt = key >> 3, key & 7
        if wt == 0:  # varint
            val, i = _read_varint(buf, i)
            yield fno, wt, val
        elif wt == 2:  # len-delimited
            ln, i = _read_varint(buf, i)
            yield fno, wt, buf[i : i + ln]
            i += ln
        elif wt == 5:  # 32-bit
            yield fno, wt, buf[i : i + 4]
            i += 4
        elif wt == 1:  # 64-bit
            yield fno, wt, buf[i : i + 8]
            i += 8
        else:
            raise ValueError(f"unsupported wire type {wt}")


def _parse_document(buf: bytes) -> tuple[str, list[tuple[str, int]], dict[str, int]]:
    """Return (relative_path, [(symbol, roles)...], {symbol: kind})."""
    rel_path = ""
    occurrences: list[tuple[str, int]] = []
    kinds: dict[str, int] = {}
    for fno, wt, val in _iter_fields(buf):
        if fno == 1 and wt == 2 and isinstance(val, bytes):
            rel_path = val.decode("utf-8", errors="replace")
        elif fno == 2 and wt == 2 and isinstance(val, bytes):  # Occurrence
            sym, roles = "", 0
            for ofno, owt, oval in _iter_fields(val):
                if ofno == 2 and owt == 2 and isinstance(oval, bytes):
                    sym = oval.decode("utf-8", errors="replace")
                elif ofno == 3 and owt == 0 and isinstance(oval, int):
                    roles = oval
            if sym:
                occurrences.append((sym, roles))
        elif fno == 3 and wt == 2 and isinstance(val, bytes):  # SymbolInformation
            sym, kind = "", 0
            for sfno, swt, sval in _iter_fields(val):
                if sfno == 1 and swt == 2 and isinstance(sval, bytes):
                    sym = sval.decode("utf-8", errors="replace")
                elif sfno == 5 and swt == 0 and isinstance(sval, int):
                    kind = sval
            if sym:
                kinds[sym] = kind
    return rel_path, occurrences, kinds


def iter_scip_documents(
    scip_bytes: bytes,
) -> Iterator[tuple[str, list[tuple[str, int]], dict[str, int]]]:
    """Yield parsed documents from a raw SCIP index (Index.documents = field 2)."""
    for fno, wt, val in _iter_fields(scip_bytes):
        if fno == 2 and wt == 2 and isinstance(val, bytes):
            yield _parse_document(val)


# ── DB load ───────────────────────────────────────────────────────────────────


def load_target_index(
    con: sqlite3.Connection, project: str, scip_bytes: bytes, path_prefix: str = "."
) -> tuple[int, int]:
    """Load one target's SCIP index; return (defined_symbols, edges).

    File paths are normalized to REPO-RELATIVE (prefixed with the target dir) so
    zone mapping and gate lookups work uniformly across sub-project targets.
    """
    n_syms = n_edges = 0
    for doc_path, occurrences, kinds in iter_scip_documents(scip_bytes):
        rel_path = doc_path if path_prefix == "." else f"{path_prefix.rstrip('/')}/{doc_path}"
        for sym, roles in occurrences:
            if sym.startswith("local "):  # file-local symbols are noise for the fleet
                continue
            if roles & ROLE_DEFINITION:
                con.execute(
                    "INSERT INTO symbols(project, symbol, kind, file) VALUES(?,?,?,?)",
                    (project, sym, kinds.get(sym, 0), rel_path),
                )
                n_syms += 1
            else:
                edge_kind = "import" if roles & ROLE_IMPORT else "ref"
                con.execute(
                    "INSERT INTO edges(src_project, src_file, dst_symbol, kind) VALUES(?,?,?,?)",
                    (project, rel_path, sym, edge_kind),
                )
                n_edges += 1
    return n_syms, n_edges


def build(
    scip_dir: Path, targets_file: Path, out: Path, graph_commit: str, crosslink_file: Path | None
) -> int:
    """Build fleet.db from downloaded scip-<slug> artifact dirs. Single-writer."""
    manifest = json.loads(targets_file.read_text(encoding="utf-8"))
    built_at = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    out.unlink(missing_ok=True)  # fresh DB every build — never merge into an old one
    con = sqlite3.connect(out)
    con.executescript(SCHEMA)
    con.execute("INSERT INTO meta VALUES('graph_commit', ?)", (graph_commit,))
    con.execute("INSERT INTO meta VALUES('built_at', ?)", (built_at,))
    con.execute("INSERT INTO meta VALUES('schema_version', '1.0')")

    ok = 0
    for target in manifest["targets"]:
        slug, path, lang = target["slug"], target["path"], target["lang"]
        project = f"emi-{slug}"
        art_dir = scip_dir / f"scip-{slug}"
        status, reason, scip_bytes_n = "UNKNOWN", "", 0
        meta_path = art_dir / "scip-meta.json"
        index_path = art_dir / "index.scip"
        if not art_dir.is_dir() or not meta_path.is_file():
            reason = "artifact missing"  # NO-MOCK: absent is UNKNOWN, never empty-OK
        else:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            status, reason = meta.get("status", "UNKNOWN"), meta.get("reason", "")
            scip_bytes_n = int(meta.get("scip_bytes", 0))
            if status == "OK":
                try:
                    n_syms, n_edges = load_target_index(
                        con, project, index_path.read_bytes(), path_prefix=path
                    )
                    if n_syms == 0:
                        status, reason = "UNKNOWN", "parsed 0 symbols (empty is not safe)"
                    else:
                        print(f"{project}: {n_syms} symbols, {n_edges} edges")
                except (ValueError, OSError, IndexError) as exc:
                    status, reason = "UNKNOWN", f"scip parse failed: {exc}"
        if status == "OK":
            ok += 1
        else:
            print(f"::warning title=fleet-graph {project} UNKNOWN::{reason}", file=sys.stderr)
        con.execute(
            "INSERT INTO targets VALUES(?,?,?,?,?,?,?,?)",
            (project, path, lang, status, reason, graph_commit, built_at, scip_bytes_n),
        )

    if crosslink_file is not None and crosslink_file.is_file():
        cross = json.loads(crosslink_file.read_text(encoding="utf-8"))
        for join in cross.get("joins", []):
            con.execute(
                "INSERT INTO crosslink VALUES(?,?,?)",
                (join["zone"], join.get("room"), join.get("owner_line")),
            )
    con.commit()

    total = len(manifest["targets"])
    summary = {
        "graph_commit": graph_commit,
        "built_at": built_at,
        "targets_total": total,
        "targets_ok": ok,
        "symbols": con.execute("SELECT COUNT(*) FROM symbols").fetchone()[0],
        "edges": con.execute("SELECT COUNT(*) FROM edges").fetchone()[0],
    }
    out.with_name("fleet-meta.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary))
    con.close()
    if ok == 0:
        print("::error::every target is UNKNOWN — no graph to publish (NO-MOCK)", file=sys.stderr)
        return 1
    return 0


# ── self-test (--check): synthesize a tiny SCIP index and round-trip it ───────


def _enc_varint(v: int) -> bytes:
    out = bytearray()
    while True:
        byte = v & 0x7F
        v >>= 7
        if v:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _enc_len(fno: int, payload: bytes) -> bytes:
    return _enc_varint((fno << 3) | 2) + _enc_varint(len(payload)) + payload


def _enc_int(fno: int, val: int) -> bytes:
    return _enc_varint(fno << 3) + _enc_varint(val)


def self_check() -> int:
    """Round-trip a synthesized index through parser + DB; verify counts."""
    occ_def = _enc_len(2, b"pkg/mod/Sym#") + _enc_int(3, ROLE_DEFINITION)
    occ_ref = _enc_len(2, b"pkg/other/Dep#") + _enc_int(3, 8)  # ReadAccess ref
    occ_local = _enc_len(2, b"local 1") + _enc_int(3, ROLE_DEFINITION)  # must be skipped
    syminfo = _enc_len(1, b"pkg/mod/Sym#") + _enc_int(5, 7)
    doc = _enc_len(1, b"services/x/mod.py") + _enc_len(2, occ_def) + _enc_len(2, occ_ref)
    doc += _enc_len(2, occ_local) + _enc_len(3, syminfo)
    index = _enc_len(2, doc)

    docs = list(iter_scip_documents(index))
    assert len(docs) == 1, f"expected 1 document, got {len(docs)}"
    rel, occs, kinds = docs[0]
    assert rel == "services/x/mod.py", rel
    assert ("pkg/mod/Sym#", ROLE_DEFINITION) in occs and ("pkg/other/Dep#", 8) in occs
    assert kinds["pkg/mod/Sym#"] == 7

    con = sqlite3.connect(":memory:")
    con.executescript(SCHEMA)
    n_syms, n_edges = load_target_index(con, "emi-test", index)
    assert n_syms == 1, f"symbols: {n_syms}"  # local symbol skipped
    assert n_edges == 1, f"edges: {n_edges}"
    row = con.execute("SELECT project, symbol, kind, file FROM symbols").fetchone()
    assert row == ("emi-test", "pkg/mod/Sym#", 7, "services/x/mod.py"), row
    print("build_fleet_graph self-check OK (wire parser + schema round-trip)")
    return 0


def main(argv: list[str]) -> int:
    """CLI entry: --check self-test or a full artifact-dir build."""
    parser = argparse.ArgumentParser(description="STEP4 fleet-graph builder")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--scip-dir", type=Path)
    parser.add_argument("--targets", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--graph-commit", default="")
    parser.add_argument("--crosslink", type=Path, default=None)
    args = parser.parse_args(argv)
    if args.check:
        with tempfile.TemporaryDirectory():
            return self_check()
    if not (args.scip_dir and args.targets and args.out and args.graph_commit):
        parser.error("--scip-dir, --targets, --out, --graph-commit are required")
    return build(args.scip_dir, args.targets, args.out, args.graph_commit, args.crosslink)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
