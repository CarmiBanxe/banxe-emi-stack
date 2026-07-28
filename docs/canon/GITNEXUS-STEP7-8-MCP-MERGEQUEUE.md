# GITNEXUS-STEP7-8-MCP-MERGEQUEUE — read-only MCP + queue re-check (PASS B)

> **STATUS: PROPOSED (singleton PR).** ⚠ SANDBOX / TRAINING.
> **Pointer-first (ADR-102):** rationale = Fable 5 consultant response §4/§3/§6
> (roadmap steps 7–8); STEP1..6 shards. This file records ONLY PASS B deltas.

## STEP7 — fleet-graph MCP server (read-only, ADR-117)

`scripts/gitnexus/fleet_graph_mcp.py` (FastMCP, stdio) serves the STEP4
`fleet-graph-db` artifact + STEP2 ownership map to agents. Tools:
`graph_freshness` · `impacted_by(file|symbol)` · `owners_of(path)` ·
`criticality_of(path)`.

**Read-only proof, by construction (unit-tested):** SQLite opened `mode=ro` at
the driver (writes raise `OperationalError`); no write tools registered; no
filesystem surface beyond the DB + two committed maps; **cross-repo answers are
DERIVED METADATA only** — the `crosslink` table baked at build time (zone →
room → owner_line), never a foreign working tree. Every response carries
`graph_commit` + `built_at`; missing/stale DB or non-OK target ⇒ UNKNOWN
objects with reasons, never empty=safe (NO-MOCK).

Activation is operator-applied via `config/gitnexus/mcp.fleet-graph.template.json`
(same manual-template contract as the gitnexus MCP template). No CI check — the
server is a served artifact; an optional `mcp-selftest` check is a PASS-B-c
decision. Deliberately separate from the product server `banxe_mcp/server.py`
(rule 70-mcp-tools): governance metadata, not banking APIs.

## STEP8 — merge-queue impact re-check (`mq-impact`)

`.github/workflows/merge-queue-impact.yml`, `merge_group`-triggered: locates the
fleet-graph run for the **merge-group head** (fresh, not PR-time), downloads
`fleet-graph-db`, re-runs `impact_gate.py --enforce` over the queue diff.
CRITICAL / cross-zone blast radius without PR label `cross-repo-ack` ⇒ FAIL;
no graph run / empty artifact / UNKNOWN verdict ⇒ **FAIL VISIBLY** with the
documented recovery: structural review (PHASE1 detect_impact) + human ack —
never a silent pass, never a blind block (freshness canon, STEP4). PR number is
derived from the `gh-readonly-queue/main/pr-<N>-…` head ref.

**PRODUCER-ONLY:** `mq-impact` is NOT in branch protection until PASS-B-c,
after observed green on real queue runs (STEP1..6 pattern).

## Freshness SLO

Queue-time re-check *is* the freshness mechanism for merges: the verdict is
always computed against the graph of the exact merge-group head. The
`fleet_graph.freshness_slo` block (max_lag 50) continues to govern long-lived
consumers (STEP7 MCP serving a downloaded main artifact) — `graph_freshness`
exposes the data needed to enforce it client-side.

## Links / rollback

STEP9 (Pact/schemathesis) adds consumer contract tests into the same queue
stage; STEP10 (Langfuse) will trace which `graph_commit` an agent consulted.
Rollback: revert the PR — server script, template, workflow, map keys, canon
and shard disappear; no state outside git + 14-day artifacts. *Singleton
ledger-PR; shard `step78-mcp-mergequeue`; I-24; ADR-117; ADR-060/120.*

## PASS-B-c decision (2026-07-28, appended — I-24)

**`mq-impact` is queue-time-only and MUST NOT be added to
`required_status_checks`.** The workflow is `merge_group`-triggered and does
not report on normal PRs (verified on PR #337's rollup); per
`GITNEXUS-REQUIRED-CHECK-PATHFILTER-FIX` (required ⇒ must always-report),
requiring it would deadlock every PR with a permanently-missing context.
Enforcement already happens where it belongs: inside the merge queue,
`impact_gate.py --enforce` runs against the exact queue head — a failing
`mq-impact` fails the merge-group and ejects the PR from the queue, which is
strictly fresher than any PR-time verdict. STEP7 (fleet-graph MCP) is a served
read-only artifact with no CI check. **PASS B is COMPLETE with NO
branch-protection change; the required-checks count stays 20.**
