# Post-mortem: Keycloak Quarkus SIGKILL on evo1 — 2026-05-04

## TL;DR

Keycloak 26.2.5 cutover (FCA CASS 15, deadline 2026-05-07) blocked 24h by Quarkus build SIGKILL on evo1 (kernel 6.17). Resolved via host migration to Legion (kernel 6.6 WSL2). Zero production downtime.

## Timeline

- 2026-05-03 22:30 — pre-GATE-A artefacts (commit 19e1cf6).
- 2026-05-04 00:30 — first SIGKILL on evo1.
- 8 retry attempts on `feat/keycloak-banxe-emi-realm-pass`: --optimized split, mem caps, Dockerfile pre-bake, dev-file fallback. All killed.
- 2026-05-04 01:17 — STOP-document 6dcfc38, P3.4 frozen.
- 2026-05-04 12:03 — Block R diagnostics (PR #45): R3 confirms evo1 kernel/cgroups bug, R4 confirms Legion works.
- 2026-05-04 12:50 — STRATEGY-B compose live on Legion, realm imported.
- 2026-05-04 13:00 — 4 clients provisioned, cross-host smoke 4/4 OK.

## Root cause

Quarkus build step receives raw SIGKILL on evo1 kernel 6.17 + cgroups v2. No OOM journal, no oomd activity, no user.slice limits. JVM heap caps, mem_limit, swap, backend choice (postgres vs dev-file), pre-bake via Dockerfile — all variants killed. Same image works on Legion kernel 6.6.

## Decision

STRATEGY-B (host migration) over STRATEGY-A (kernel debug):
- 3 days to deadline.
- Legion proven working in R4.
- Tailscale mesh = no extra networking work.
- KC_DB=dev-file accepted as G-IAM-09 tech debt.

## What worked
- Block R structured diagnostic R1-R5.
- Tailscale mesh routing.
- realm JSON `_*` meta-field stripping (Jackson FAIL_ON_UNKNOWN_PROPERTIES).
- `sslRequired=NONE` for Tailscale-only deployment.

## What did not work
- 8 JVM/cgroups tuning variants on evo1.

## Tech debt accepted
- G-IAM-09: KC_DB=dev-file (H2). Postgres migration target 2026-05-31.
- Backup of `keycloak_data` volume preserves CASS 15 audit retention.
