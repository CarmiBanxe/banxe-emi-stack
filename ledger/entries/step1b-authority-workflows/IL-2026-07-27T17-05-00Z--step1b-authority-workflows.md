---
il_ts: 2026-07-27T17:05:00Z
session_id: step1b-authority-workflows
source: agent-factory
status: PROPOSED
---
### STEP1b: port ledger/serialize authority workflows emi-stack <- architecture

- **Instruction:** Port the three authority check-producers from banxe-architecture so
  guardian-ledger, ledger-append-only and main-merge-serialize become REAL contexts in
  banxe-emi-stack CI. Require them in branch protection ONLY after observed green on a
  live PR (STEP1c — separate operator action; branch protection NOT touched here).
- **Files:** .github/workflows/guardian.yml (+2 jobs: guardian-ledger,
  ledger-append-only; + merge_group trigger; existing guardian-factory/project jobs
  unchanged), .github/workflows/main-serialize.yml (new), this shard.
- **Ground-truth correction:** ledger-append-only is a JOB inside architecture
  guardian.yml (ADR-057), not a separate workflow — mirrored accordingly, no extra file.
- **emi-stack adaptations (deliberate, flagged for STEP1c review):**
  (1) ADR-056 coupling binds GOVERNANCE paths only (docs/canon/, docs/adr/, .claude/,
  config/gitnexus/, ledger/, INSTRUCTION-LEDGER.md) — verbatim architecture semantics
  would demand a shard on every feature PR in a code repo;
  (2) ledger-append-only also protects ledger/entries/** from modify/rename/delete
  (I-24) since INSTRUCTION-LEDGER.md is tracked here (architecture rebuilds it in CI);
  (3) main-serialize resolves OK instantly in merge_group (queue already serializes).
- **Invariants:** I-24 (new files + this shard only; no existing entry touched);
  I-27 (gates fail-closed, human unblocks); ADR-117 (emi-stack scope only);
  ADR-060/120 (landed via agent/factory/EMISTACK01/step1b-authority-workflows from a
  dedicated worktree); singleton ledger-PR (this shard lands alone with its change).
- **Reference:** Fable 5 consultant response — GitNexus cross-repo control stack,
  §3 Enforcement layers / §6 roadmap step 1; STEP1 shard step1-enforcement-emi-parity.
- **Status:** PROPOSED — operator merge required. No mint issued.
