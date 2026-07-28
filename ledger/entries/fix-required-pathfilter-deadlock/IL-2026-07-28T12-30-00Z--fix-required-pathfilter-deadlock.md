---
il_ts: 2026-07-28T12:30:00Z
session_id: fix-required-pathfilter-deadlock
source: agent-factory
status: PROPOSED
---
### FIX: required-check + path-filter deadlock (always-report pattern)

- **Incident:** PASS-A-c made contract-diff + sbom REQUIRED while
  contracts-sbom.yml kept pull_request paths: filters; PR #337 touched none of
  them => contexts never reported => PR BLOCKED (everything else green).
  Systemic for every non-contract PR. Audit found the same latent deadlock in
  scip-index.yml (required: scip-index) and fleet-graph.yml (required:
  fleet-graph, impact-gate). Clean: codeowners-check, guardian, main-serialize;
  merge-queue-impact is merge_group-only (rule applies at PASS-B-c).
- **Fix (canonical always-report pattern):** paths: removed from pull_request
  triggers of the three workflows; a pure `git diff --name-only BASE HEAD`
  relevance step (no new actions — dorny/paths-filter deliberately avoided, no
  new pins) gates the HEAVY steps only; irrelevant diffs end
  COMPLETED/SUCCESS with an explicit "no relevant changes" notice. Gate
  strength unchanged for relevant diffs (full oasdiff/SBOM/index/build,
  NO-MOCK preserved). Regex semantics tested: docs-only => no-op; .py/deps/
  workflow changes => full run. Self-unblocking: each relevance set includes
  its own workflow file, so all five contexts run FULL on this fix PR.
- **Files:** .github/workflows/contracts-sbom.yml (paths removed, per-job rel
  steps, no-op notices), .github/workflows/scip-index.yml (manifest rel output,
  matrix job-level skip, aggregator no-op branch), .github/workflows/
  fleet-graph.yml (rel step + conditional build/gate + no-op notices),
  docs/canon/GITNEXUS-REQUIRED-CHECK-PATHFILTER-FIX.md (new), this shard.
  ownership.map.json unchanged (path filters were never documented there).
- **Post-merge:** PR #337 requires rebase/update-branch so its contexts run and
  report. Branch protection NOT modified.
- **Invariants:** I-24 (append-only; governance paths touched — shard included);
  I-27 (no gate weakened; skips are explicit and logged); ADR-060/120 (branch
  agent/factory/EMISTACK01/fix-required-pathfilter-deadlock, dedicated
  worktree); singleton ledger-PR; all actions remain SHA-pinned.
- **Reference:** Fable 5 consultant response §3/§7 (merge-queue check
  resolution; anti-pattern "checks that never fire deadlock the queue");
  STEP1b merge_group precedent.
- **Status:** PROPOSED — operator merge required. No mint issued.
