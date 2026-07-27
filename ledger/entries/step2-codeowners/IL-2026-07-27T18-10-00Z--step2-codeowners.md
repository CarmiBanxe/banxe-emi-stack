---
il_ts: 2026-07-27T18:10:00Z
session_id: step2-codeowners
source: agent-factory
status: PROPOSED
---
### STEP2: zone CODEOWNERS as generated artifact (Fable 5 rollout, emi-stack)

- **Instruction:** Replace the non-functional CODEOWNERS (every rule pointed at
  @mmber — an unrelated non-collaborator account; GitHub codeowners API reported
  8 errors) with a generated, zone-based file. Source of truth =
  config/gitnexus/ownership.map.json (zones mirror PHASE1 criticality domains;
  roles are operator-binding-required placeholders from agent-authority.md; only
  enforceable identity today = @CarmiBanxe, USER-OWNED repo). CI job
  codeowners-coverage enforces map<->CODEOWNERS drift, CRITICAL-pattern reality,
  and freshness (warn past review_by 2026-10-27 — stale map surfaces, never blocks).
- **Files:** .github/CODEOWNERS (regenerated), config/gitnexus/ownership.map.json
  (new SoT), scripts/gitnexus/gen_codeowners.py (new, stdlib),
  .github/workflows/codeowners-check.yml (new, context codeowners-coverage),
  docs/canon/GITNEXUS-STEP2-CODEOWNERS.md (new), this shard.
- **Follow-ups (separate operator actions):** STEP2c = enable "Require review from
  Code Owners" + require codeowners-coverage after observed green + codeowners-errors
  API shows 0. STEP3+ extension points documented in canon doc.
- **Invariants:** I-24 (new files + regenerated artifact; no ledger entry touched);
  I-27 (staleness warns, humans decide); ADR-117 (repo scope only); ADR-060/120
  (agent/factory/EMISTACK01/step2-codeowners via dedicated worktree); singleton
  ledger-PR; Fable 5 rules (freshness metadata, no god-server, GitNexus-replaceable).
- **Reference:** Fable 5 consultant response §3/§6 roadmap step 2; PR #331 (PHASE0/1),
  PR #332 (STEP1b).
- **Status:** PROPOSED — operator merge required. No mint issued.
