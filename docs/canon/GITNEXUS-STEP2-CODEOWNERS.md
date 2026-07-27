# GITNEXUS-STEP2-CODEOWNERS — zone ownership as code (emi-stack only)

> **STATUS: PROPOSED (singleton PR).** ⚠ SANDBOX / TRAINING.
> **Pointer-first (ADR-102):** fleet control-stack rationale = Fable 5 consultant
> response (GitNexus cross-repo control stack, §3 Enforcement / §6 roadmap step 2);
> STEP1/1b shards `step1-enforcement-emi-parity`, `step1b-authority-workflows`.
> This file records ONLY what STEP2 changes in **banxe-emi-stack**.

## Goal

Reviewer routing enforced **by zone, server-side**: every PR touching a governed path
requires review from that zone's owner, derived from one machine-readable map — not
from tribal knowledge. Independently valuable without any GitNexus runtime
(Fable 5 hard rule: the PolyForm-NC engine stays replaceable).

## Ownership model

- **Source of truth:** `config/gitnexus/ownership.map.json` (zones → patterns →
  criticality → role → GitHub owners). `.github/CODEOWNERS` is a **generated
  artifact** (`scripts/gitnexus/gen_codeowners.py`); never hand-edit both — CI job
  `codeowners-coverage` fails on drift.
- **Zones** mirror the STEP1b/PHASE1 criticality domains (`CATEGORY_MAP` in
  `scripts/gitnexus/detect_impact.py`): migrations, ledger-core, compliance-aml,
  consumer-duty, safeguarding-recon, reporting-fca, audit-append-only (CRITICAL);
  infra-governance, api-contracts, agents (HIGH); frontend (MEDIUM).
- **Identity reality (found during STEP2 audit):** this is a USER-OWNED repo — only
  collaborators with write access are enforceable owners, and today that is exactly
  `@CarmiBanxe`. The **previous CODEOWNERS pointed every rule at `@mmber`, an
  unrelated non-collaborator GitHub account (8 errors in the GitHub codeowners
  API) — the file was silently non-functional.** STEP2 replaces it.
- **Roles are placeholders, not people:** MLRO/CFO/CTIO/Compliance Officer
  annotations are comments carried from `agent-authority.md` and marked
  **operator-binding-required** — when the GitHub org and teams exist, bind each
  role to a real team in the map and regenerate. No invented humans (NO-MOCK).

## Escalation / default rules

- Default owner `*` → `@CarmiBanxe` (Operator, CEO SMF1). Last-match-wins puts zone
  rules above the default.
- Zone with no bound team ⇒ falls back to default owner — never ownerless.
- Enforcement switch is branch protection "Require review from Code Owners"
  (operator action, STEP2c, after this PR merges and the GitHub codeowners-errors
  API reports 0 errors).

## Freshness / review policy (Fable 5 hard rule)

The map carries `freshness.generated_at` + `freshness.review_by` (quarterly).
`codeowners-coverage` **warns** when `review_by` is past and **fails** when a
CRITICAL pattern no longer matches a real directory. Staleness surfaces; it never
hard-blocks merges (I-27 — humans decide). A stale map is more dangerous than no
map: the warning is the loop that keeps it alive.

## Connection to STEP3–STEP10 (extension points, no implementation here)

- **STEP3 (SCIP):** per-zone `scip_index` flag will opt zones into symbol-graph
  granularity; indexers publish artifacts keyed by the same zone names.
- **STEP4 (fleet graph):** `zones[].zone` is the join key to banxe-architecture's
  `org-path-ownership.map.yaml` departments; the fleet builder consumes both maps
  read-only (ADR-117: no cross-repo writes, metadata only).
- **STEP5–6 (oasdiff / SBOM):** contract and dependency findings route to the owning
  zone's reviewers via this same map.
- **STEP7 (fleet-graph MCP):** serves zone+owner metadata to agents — derived data
  only, never foreign working trees.
- **STEP8 (merge-time impact queue):** zone criticality feeds ack thresholds
  (CRITICAL cross-zone impact ⇒ owner acknowledgement required).

## Rollback

Revert the PR — CODEOWNERS returns to its previous (non-functional) state; no state
outside git. *Singleton ledger-PR; shard `step2-codeowners`; I-24 append-only.*
