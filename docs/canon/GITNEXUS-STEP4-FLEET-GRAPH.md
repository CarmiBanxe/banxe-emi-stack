# GITNEXUS-STEP4-FLEET-GRAPH — fleet graph + impact gate (emi-stack)

> **STATUS: PROPOSED (singleton PR).** ⚠ SANDBOX / TRAINING.
> **Pointer-first (ADR-102):** rationale = Fable 5 consultant response §2/§3/§6
> (roadmap step 4); STEP1/1b/2/3 shards. This file records ONLY STEP4 deltas.

## What the graph is

One SQLite DB per build (`fleet-graph-db` artifact: `fleet.db` + `fleet-meta.json`)
built from the STEP3 SCIP artifacts of the SAME commit by
`scripts/gitnexus/build_fleet_graph.py`. The `.scip` protobuf is parsed with a
minimal stdlib wire-format reader (Index.documents=2 → Document → Occurrence
symbol/roles) — **no scip CLI, no protoc, no new tools**; the substrate stays
engine-neutral (Fable 5: GitNexus replaceable; PolyForm-NC engine not required).

## Schema

| table | columns | notes |
|---|---|---|
| `meta` | key, value | `graph_commit`, `built_at`, `schema_version` — freshness is data |
| `targets` | project, path, lang, **status(OK/UNKNOWN)**, reason, graph_commit, built_at, scip_bytes | NO-MOCK is first-class |
| `symbols` | id, project, symbol, kind, file | definitions only; `local *` skipped; **file paths repo-relative** (target prefix applied) |
| `edges` | id, src_project, src_file, dst_symbol, kind(ref/import) | reverse-dep source |
| `crosslink` | zone, room, owner_line | derived cross-repo metadata (below) |

## Impact gate (`impact-gate`, ADVISORY this step)

For PR-changed files: defined symbols → reverse deps → zones (STEP2 map).
Verdicts: `REPORT` · `ACK_REQUIRED` (cross-zone impact OR CRITICAL per
`fleet_graph.impact_gate.thresholds`; label `cross-repo-ack` requested) ·
`UNKNOWN` (changed file's target not OK — **fail-closed-visible**, degrade to
structural review + human ack; never empty-safe). Blind spots (any non-OK
target) are always listed. Enforcement is OFF (`--enforce` unused) until
STEP4c/STEP8 — I-27: the gate proposes, humans decide.

## Cross-repo rule (ADR-117)

The ONLY cross-repo surface is `config/gitnexus/fleet.crosslink.json`: zone →
room → executive owner_line, **derived as data** from banxe-architecture
`org-path-ownership.map.yaml` @ `94ce94c` (S1 ORG-MAP). CI never reads the
architecture working tree. 4 unambiguous joins; 7 zones left TODO-operator
(NO-MOCK — not guessed). Regenerate manually when the source map moves.

## Freshness SLO

Per-PR DBs are same-commit by construction (`graph_commit` = PR head). The SLO
(`fleet_graph.freshness_slo`: max_lag_commits 50, stale ⇒ degrade to structural
+ human ack) activates at STEP7 (MCP serves the latest **main** DB) and STEP8
(merge-queue re-check). Every gate verdict prints `graph_commit` + `built_at`.

## Single-writer

One builder job, concurrency group `fleet-graph-<ref>`, fresh DB per run
(`out.unlink()` first — never merge into an old graph). No other writer exists.

## STEP7 pointer / rollback

STEP7 fleet-graph MCP serves `fleet-graph-db` read-only (metadata only, no
foreign working trees). Rollback: revert the PR; artifacts expire in 14 days.
*Singleton ledger-PR; shard `step4-fleet-graph`; I-24 append-only.*
