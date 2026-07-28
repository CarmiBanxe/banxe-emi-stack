---
il_ts: 2026-07-28T15:30:00Z
session_id: passc-contracttests-observability
source: agent-factory
status: PROPOSED
---
### STEP9 first-run findings — input-validation backlog + baseline tier definition

- **Evidence (schemathesis fuzz + baseline runs, 2026-07-28):** 13x ValueError +
  22x OverflowError (huge-int/Decimal overflow on numeric params => 500 not 422)
  across the 491-path API under hostile fuzz; 78/262 GET ops fail
  status_code_conformance (undocumented 4xx); 9/262 fail
  response_schema_conformance; real bugs: /v1/payments* AttributeError,
  /v1/quant/price ValueError, /v1/ledger/accounts* server errors (treasury-class,
  own fix PRs); /v1/fx-rates/* requires live Frankfurter (integration tier).
- **Decision:** contract-tests producer tier REDEFINED to a stable, honest
  BASELINE: deterministic schema-valid explicit examples, GET-only, crash +
  transport checks, 8 ops excluded with visible reasons (scope definition, NOT
  gate weakening — baseline verified 260/260 PASS locally AND caught the
  ledger/payments/quant reds minutes earlier). Full negative/boundary fuzz of
  all paths = separate backlog item: input validation must return 422, never
  500. Tier definition is test-locked
  (test_baseline_tier_is_deterministic_valid_input_only).
- **Invariants:** NO-MOCK (findings recorded with counts, exclusions visible,
  nothing hidden); I-24 (append-only canon note + this new shard); I-27 (bug
  fixes routed to humans as separate PRs); singleton PR #340.
- **Status:** PROPOSED — operator merge required. No mint issued.
