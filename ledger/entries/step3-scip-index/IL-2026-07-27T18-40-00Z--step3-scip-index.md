---
il_ts: 2026-07-27T18:40:00Z
session_id: step3-scip-index
source: agent-factory
status: PROPOSED
---
### STEP3: SCIP symbol-graph producer (Fable 5 rollout, emi-stack)

- **Instruction:** Introduce SCIP indexing as ground-truth symbol graph. 7 targets
  (2 python roots: repo root + services/safeguarding-engine; 5 typescript apps:
  banking-mobile, banking-web, mobile, web, frontend) enumerated deterministically
  by scripts/gitnexus/scip_manifest.py into config/gitnexus/scip.targets.json
  (generated, drift-checked — same SoT contract as STEP2 CODEOWNERS). CI producer
  .github/workflows/scip-index.yml: matrix fan-out, pinned indexers verified live
  on npm (@sourcegraph/scip-python@0.6.6, @sourcegraph/scip-typescript@0.4.0),
  artifact scip-<slug> = index.scip + scip-meta.json with graph_commit + built_at
  (Fable 5 freshness rule). NO-MOCK: indexer failure => status UNKNOWN visible,
  zero-byte index never OK, all-UNKNOWN => systemic FAIL. PRODUCER-ONLY: context
  scip-index NOT added to branch protection (STEP3c after observed green).
- **ownership.map.json:** append-only population of the STEP2 extension point —
  zones[].scip_index (true except infra-governance), top-level scip block
  (targets_file, pinned indexers, artifact contract), extension_points.step3_scip_status.
  STEP2 fields untouched; gen_codeowners.py --check still green (render-neutral).
- **Files:** .github/workflows/scip-index.yml (new), scripts/gitnexus/scip_manifest.py
  (new), config/gitnexus/scip.targets.json (new, generated),
  config/gitnexus/ownership.map.json (append-only keys),
  docs/canon/GITNEXUS-STEP3-SCIP-INDEX.md (new), this shard.
- **Invariants:** I-24 (append-only: new files + appended keys; no ledger entry
  touched; this PR touches governance paths and carries this shard — satisfies its
  own guardian-ledger gate); I-27 (UNKNOWN surfaces, humans decide); ADR-117
  (emi-stack scope; SCIP artifacts are repo-local); ADR-060/120 (landed via
  agent/factory/EMISTACK01/step3-scip-index from dedicated worktree); singleton
  ledger-PR; Fable 5 rules (SCIP over LSIF, self-hosted OSS, freshness explicit,
  GitNexus-replaceable).
- **Reference:** Fable 5 consultant response §2/§6 roadmap step 3; PR #331 (PHASE0/1),
  PR #332 (STEP1b), STEP2 shard step2-codeowners.
- **Status:** PROPOSED — operator merge required. No mint issued.
