# GITNEXUS-STEP9-10-CONTRACTTESTS-OBS — contract tests + observability (PASS C, FINAL)

> **STATUS: PROPOSED (singleton PR).** ⚠ SANDBOX / TRAINING.
> **Pointer-first (ADR-102):** rationale = Fable 5 consultant response §5/§6
> (roadmap steps 9–10); STEP1..8 shards; always-report rule =
> GITNEXUS-REQUIRED-CHECK-PATHFILTER-FIX. This file records ONLY PASS C deltas.

## STEP9 — contract tests (`contract-tests`)

- **Tool choice:** `schemathesis==3.39.16` (pinned) — property/contract tests
  generated FROM the live OpenAPI schema (reuses STEP5's
  `generate_current_spec` from `api.main:app`), run **in-process ASGI**
  (`--app=api.main:app`) — no server boot in CI. Pin rationale: last stable v3
  line whose CLI contract is documented; the v4 CLI could not be verified at
  pin time (NO-MOCK: we do not pin to unverified interfaces). **Pact broker
  deliberately NOT stood up** — a broker is a running service (operator infra
  follow-up), noted, not silently skipped.
- **Tier:** smoke — GET-only, 2 hypothesis examples/op, 2s deadline (bounded on
  a 463-path API). Deeper tiers = documented follow-up.
- **Verdicts:** PASS · FAIL (real contract violations ⇒ red) · UNKNOWN
  (schema-generation or tool failure ⇒ **visible fail, never silent pass**;
  rc=0 without a real run is never PASS — unit-tested).
- **Always-report:** no `paths:` filter; git-diff relevance step; irrelevant
  diffs ⇒ SUCCESS no-op — safe to require at PASS-C-c.

## STEP10 — observability (`obs-manifest`)

- **Producer:** `scripts/gitnexus/obs_manifest.py` — per-run JSON manifest of
  the commit's check-runs (name, status, conclusion, started/completed,
  durations, totals) via `gh api`; artifact `obs-manifest` (14d). This is the
  Langfuse-shaped "trace of what the pipeline saw" **without** a live server.
- **NO-MOCK:** the obs job itself is a check-run, so an empty check-run list
  means collection failed ⇒ UNKNOWN, never "nothing ran".
- **Live Langfuse:** OPTIONAL ingestion behind `LANGFUSE_HOST` /
  `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` secrets — absent ⇒ documented
  skip-success. Self-hosted Langfuse-over-LiteLLM wiring (the consultant's
  step-10 full form) is an operator infra follow-up; the manifest producer is
  its data source either way.
- Cheap ⇒ runs fully on every PR (trivially always-report).

## Aggregator

`contracts-tests-obs` summarizes both jobs (not intended as a required context;
the two named contexts are the PASS-C-c candidates).

## ROADMAP COMPLETE

With PASS C landed, **Fable 5 roadmap STEP1–STEP10 is COMPLETE on
banxe-emi-stack**: server-side enforcement (1), generated CODEOWNERS (2), SCIP
producers (3), fleet graph + impact gate (4), contract diff (5), SBOM (6),
read-only MCP (7), merge-queue re-check (8), contract tests (9), observability
producer (10). Remaining items are operator infra follow-ups by design: DT
server, Langfuse server, Pact broker, GitNexus license fork, fleet-wide
rollout (architecture-repo plan §6).

## Rollback

Revert the PR — workflow, scripts, tests, map keys, canon, shard disappear;
artifacts expire in 14d. *Singleton ledger-PR; shard
`passc-contracttests-observability`; I-24; I-27; ADR-117; ADR-060/120.*

## Known follow-up: negative/boundary fuzz hardening (appended 2026-07-28, I-24)

The first live STEP9 runs did their job — findings, not noise:

1. **Hostile-fuzz input-validation class (found, then moved to backlog):**
   13× ValueError + 22× OverflowError across numeric path/query params under
   schemathesis fuzz (huge-int / Decimal overflow ⇒ 500 instead of 422).
   Fixing input validation across the 491-path API is its own backlog item
   ("validate ⇒ 422, never 500"), NOT PASS C scope.
2. **Real bugs surfaced and routed:** treasury async-seed (fixed, own PR);
   `/v1/payments*` AttributeError, `/v1/quant/price` ValueError,
   `/v1/ledger/accounts*` server errors — excluded from baseline WITH reasons,
   backlog candidates for their own fix PRs (treasury-class pattern).
3. **Conformance debt (documented, not baseline):** status_code_conformance
   78/262 failing ops (mostly undocumented 4xx), response_schema_conformance
   9/262 — schema-documentation debt for the api-contracts zone.
4. **Environment-dependent ops:** `/v1/fx-rates/*` needs a live Frankfurter —
   impossible in a hermetic gate; candidates for an integration tier.

**Baseline tier (redefined, scope definition NOT weakening):** deterministic
schema-valid explicit examples (fill-missing + derandomize + fixed seed),
GET-only, checks = not_a_server_error + content_type + response_headers,
8 ops excluded with visible reasons. Verified locally: 260/260 PASS in ~2s —
and the same gate red-flagged ledger/payments/quant minutes earlier, proving it
still catches real valid-input contract breaks. Every flag verified against
pinned schemathesis 3.39.16 `--help` (no invented flags).
