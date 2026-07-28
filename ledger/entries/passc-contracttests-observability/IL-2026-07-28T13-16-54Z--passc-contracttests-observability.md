---
il_ts: 2026-07-28T13:16:54Z
session_id: passc-contracttests-observability
source: agent-factory
status: PROPOSED
---
### PASS C (STEP9+STEP10, FINAL): contract tests + observability — Fable 5 STEP1-10 COMPLETE

- **Instruction:** One singleton PR, final roadmap pass. STEP9: context
  `contract-tests` — schemathesis==3.39.16 (pinned; v3 CLI in-process ASGI
  --app=api.main:app, no server boot; v4 CLI unverifiable at pin time —
  NO-MOCK, documented) over the live OpenAPI schema (reuses STEP5 generator);
  smoke tier (GET-only, 2 examples/op, 2s deadline); verdicts PASS/FAIL/UNKNOWN
  — schema/tool failure => UNKNOWN visible fail, rc=0 without a real run is
  never PASS (unit-tested); Pact broker deliberately deferred (running-service
  infra). STEP10: context `obs-manifest` — scripts/gitnexus/obs_manifest.py
  emits per-run JSON manifest of the commit's check-runs (durations, totals)
  via gh api; artifact obs-manifest 14d; empty list => UNKNOWN (the job itself
  is a check-run); live Langfuse ingestion OPTIONAL behind LANGFUSE_* secrets
  (skip-success unset; Langfuse-over-LiteLLM = operator infra follow-up).
- **Always-report (canon GITNEXUS-REQUIRED-CHECK-PATHFILTER-FIX):** no paths:
  filters; contract-tests uses the git-diff relevance step with SUCCESS no-op;
  obs-manifest is cheap and runs fully — both safe to require at PASS-C-c.
- **Files:** .github/workflows/contracts-tests-obs.yml (new: contract-tests +
  obs-manifest + aggregator, actions SHA-pinned), scripts/gitnexus/
  contract_tests.py (new), scripts/gitnexus/obs_manifest.py (new),
  tests/test_gitnexus/test_contract_tests_obs.py (new, 7 tests; suite 17/17),
  config/gitnexus/ownership.map.json (append-only: contract_tests +
  observability blocks + step9/step10 extension statuses; ALL prior keys
  untouched — gen_codeowners/scip_manifest/contract_check checks green),
  docs/canon/GITNEXUS-STEP9-10-CONTRACTTESTS-OBS.md (new), this shard.
- **PRODUCER-ONLY:** neither context required until PASS-C-c (observed green).
- **ROADMAP:** Fable 5 STEP1-10 COMPLETE on banxe-emi-stack (STEP1 server-side
  enforcement; 2 CODEOWNERS; 3 SCIP; 4 fleet graph+impact gate; 5 oasdiff;
  6 SBOM; 7 read-only MCP; 8 mq re-check; 9 contract tests; 10 observability).
  Remaining = operator infra follow-ups by design (DT/Langfuse/Pact servers,
  GitNexus license fork, fleet-wide rollout per architecture plan §6).
- **Invariants:** I-24 (append-only; governance paths touched — shard
  included); I-27 (all reds are visible and human-resolved); ADR-117; ADR-060
  (lowercase slug)/120 (dedicated worktree); singleton ledger-PR; NO-MOCK
  throughout; all pins verified live (pypi schemathesis 3.39.16).
- **Reference:** Fable 5 consultant response §5/§6 roadmap steps 9-10;
  STEP1..8 + fix/close shards.
- **Status:** PROPOSED — operator merge required. No mint issued.
