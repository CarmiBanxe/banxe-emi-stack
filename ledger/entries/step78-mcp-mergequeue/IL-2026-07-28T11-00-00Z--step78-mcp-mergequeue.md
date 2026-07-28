---
il_ts: 2026-07-28T11:00:00Z
session_id: step78-mcp-mergequeue
source: agent-factory
status: PROPOSED
---
### PASS B (STEP7+STEP8): read-only fleet-graph MCP + merge-queue impact re-check

- **Instruction:** One singleton PR. STEP7: scripts/gitnexus/fleet_graph_mcp.py —
  FastMCP stdio server over the STEP4 fleet-graph-db artifact + STEP2 ownership
  map; tools graph_freshness / impacted_by(file|symbol) / owners_of /
  criticality_of; READ-ONLY by construction (sqlite mode=ro — writes raise,
  unit-tested; zero write tools; cross-repo surface = baked crosslink table,
  derived metadata only, ADR-117); every response carries graph_commit+built_at;
  missing/stale/non-OK => UNKNOWN objects, never empty=safe (NO-MOCK);
  operator-applied template config/gitnexus/mcp.fleet-graph.template.json.
  STEP8: .github/workflows/merge-queue-impact.yml — merge_group-triggered
  context mq-impact re-runs impact_gate.py --enforce against the fleet graph of
  the merge-group head (fresh, not PR-time); CRITICAL/cross-zone without label
  cross-repo-ack => FAIL; no run/empty artifact/UNKNOWN => visible FAIL with
  documented degrade (structural review + human ack). PR number derived from
  gh-readonly-queue head_ref.
- **Files:** scripts/gitnexus/fleet_graph_mcp.py (new),
  tests/test_gitnexus/test_fleet_graph_mcp.py (new, 10 tests: read-only proof,
  UNKNOWN-on-missing, freshness fields, derived-crosslink),
  config/gitnexus/mcp.fleet-graph.template.json (new),
  .github/workflows/merge-queue-impact.yml (new, actions SHA-pinned),
  config/gitnexus/ownership.map.json (append-only: mcp + merge_queue blocks +
  extension_points statuses; STEP2..6 keys untouched — gen_codeowners /
  scip_manifest / contract_check checks green),
  docs/canon/GITNEXUS-STEP7-8-MCP-MERGEQUEUE.md (new), this shard.
- **PRODUCER-ONLY:** mq-impact not in branch protection (PASS-B-c after green
  queue runs); MCP has no CI check (served artifact; optional mcp-selftest =
  PASS-B-c decision).
- **Invariants:** I-24 (append-only; governance paths touched — shard included);
  I-27 (ack label = human decision; UNKNOWN degrades to human review); ADR-117
  (read-only MCP, derived metadata only); ADR-060/120 (branch
  agent/factory/EMISTACK01/step78-mcp-mergequeue, lowercase slug, dedicated
  worktree); singleton ledger-PR; Fable 5 (no god server, freshness explicit,
  stale => degrade not blind-block, NO-MOCK).
- **Reference:** Fable 5 consultant response §3/§4/§6 roadmap steps 7–8;
  STEP1..6 shards; rule .claude/rules/70-mcp-tools.md (deliberate governance-
  server separation from banxe_mcp/server.py).
- **Status:** PROPOSED — operator merge required. No mint issued.
