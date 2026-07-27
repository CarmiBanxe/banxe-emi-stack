---
il_ts: 2026-07-27T15:24:40Z
session_id: gitnexus01-emi-bootstrap
source: agent-factory
status: PROPOSED
---
### GITNEXUS01 emi-stack PHASE0+PHASE1 bootstrap (governance + structural code-contour)

- **Instruction:** Bootstrap GitNexus MODE for banxe-emi-stack: sandbox env guard,
  inert opt-in pre-commit impact gate, structural-only detect_impact (no external
  engine calls), MCP template (operator-applied), pointer-first PHASE0/PHASE1 canon
  docs. Mirrors banxe-architecture GITNEXUS01 phase1/2 scoped to this repo (ADR-117).
- **Files:** .githooks/pre-commit.gitnexus, scripts/gitnexus/gitnexus_env.sh,
  scripts/gitnexus/detect_impact.py, config/gitnexus/mcp.gitnexus.template.json,
  docs/canon/GITNEXUS-PHASE0-EMI-STACK-VERIFY.md,
  docs/canon/GITNEXUS-PHASE1-EMI-STACK-CODE-CONTOUR.md, README.md (§GitNexus hook),
  .githooks/pre-commit (2-line opt-in chain, GITNEXUS_PRECOMMIT=1 guarded).
- **Invariants:** I-24 append-only (new shard, no IL modified); I-27 (gate proposes,
  operator acks via GITNEXUS_ACK=1); no runtime AI activation; license
  PolyForm-Noncommercial → sandbox-only (fleet STEP15 gate governs PROD).
- **Status:** PROPOSED — singleton PR, operator merge required. No mint issued.
