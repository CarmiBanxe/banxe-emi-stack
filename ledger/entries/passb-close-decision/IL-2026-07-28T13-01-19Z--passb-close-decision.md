---
il_ts: 2026-07-28T13:01:19Z
session_id: passb-close-decision
source: agent-factory
status: PROPOSED
---
### PASS-B-c: close decision — mq-impact intentionally NOT required (count stays 20)

- **Landed:** STEP7 (read-only fleet-graph MCP server + template + 10 unit
  tests) and STEP8 (merge-queue impact re-check, context mq-impact) merged via
  PR #337.
- **Decision:** mq-impact is INTENTIONALLY NOT added to required_status_checks.
  Grounds: .github/workflows/merge-queue-impact.yml is merge_group-ONLY — the
  context does not report on normal PRs (verified: PR #337 rollup had no
  mq-impact context). Per canon GITNEXUS-REQUIRED-CHECK-PATHFILTER-FIX
  (required => must always-report), requiring it would recreate the
  missing-context deadlock on every PR. Enforcement is already correct by
  STEP8 design (Fable 5 §3/§7): impact_gate --enforce runs INSIDE the merge
  queue against the exact queue head; a red mq-impact fails the merge group
  and ejects the PR — fresher and stricter than any PR-time required check.
- **STEP7 posture:** fleet-graph MCP is a served read-only artifact; no CI
  check exists or is needed; optional mcp-selftest explicitly declined at
  PASS-B-c (no new required contexts).
- **PASS-B-c result:** NO branch-protection change; required-checks count
  stays 20. ownership.map.json untouched.
- **Invariants:** I-24 (new shard + append-only note in
  docs/canon/GITNEXUS-STEP7-8-MCP-MERGEQUEUE.md; nothing modified/deleted);
  I-27 (queue-time gate keeps human ack via cross-repo-ack label); ADR-117
  unchanged; ADR-060/120 (branch agent/factory/EMISTACK01/passb-close-decision,
  dedicated worktree); singleton ledger-PR (this shard + doc note land alone).
- **Reference:** canon GITNEXUS-REQUIRED-CHECK-PATHFILTER-FIX; canon
  GITNEXUS-STEP7-8-MCP-MERGEQUEUE (PASS-B-c section); Fable 5 consultant
  response §3 (merge queue) / §7 (deadlock anti-pattern); shards
  step78-mcp-mergequeue, fix-required-pathfilter-deadlock.
- **Status:** PROPOSED — operator merge required. No mint issued.
