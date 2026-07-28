# GITNEXUS-STEP5-6-CONTRACTS-SBOM — contract gate + SBOM (emi-stack, PASS A)

> **STATUS: PROPOSED (singleton PR).** ⚠ SANDBOX / TRAINING.
> **Pointer-first (ADR-102):** rationale = Fable 5 consultant response §2/§5/§6
> (roadmap steps 5–6); STEP1..4 shards; API rules = `.claude/rules/20-api-contracts.md`.
> This file records ONLY the PASS A deltas.

## STEP5 — contract breaking-change gate (`contract-diff`)

- **What:** oasdiff (pinned **v1.26.1** release binary) diffs the LIVE OpenAPI
  spec generated from `api.main:app` against the committed baseline
  `apps/.openapi-snapshot.json` (463 paths; also consumed by
  `scripts/proto-sync.py` — it is real infrastructure, not a fixture). Changed
  STATIC specs (`services/payment/openapi.yml`) are additionally diffed against
  their base-revision content.
- **Verdicts:** `NON_BREAKING` · `BREAKING` (FAILS without PR label
  `api-breaking-ack`; with the label — warning, human accountability recorded) ·
  `UNKNOWN` (generation/oasdiff failure — **fails visibly, never passes
  silently**, NO-MOCK).
- **Baseline refresh policy:** ONLY intentional —
  `python3 scripts/gitnexus/contract_check.py --refresh-baseline`, committed in
  the same PR as the API change plus the ack label, reviewed by the
  api-contracts zone owner. CI never auto-overwrites the baseline; a refresh
  that rides along unnoticed would mask breaking changes — that is the exact
  failure mode this policy exists to prevent.

## STEP6 — SBOM producer (`sbom`)

- **What:** CycloneDX JSON SBOMs — Python via `cyclonedx-bom==7.3.1`
  (requirements mode, no env install) and frontend via
  `@cyclonedx/cyclonedx-npm@6.0.0` (`--package-lock-only`). Artifact
  `sbom-cyclonedx`, retention 14d.
- **NO-MOCK:** an SBOM with 0 components is a tool failure, not a clean bill —
  the job FAILS.
- **Dependency-Track:** OPTIONAL. Upload happens only when operator secrets
  `DT_API_KEY` + `DT_URL` exist; absent ⇒ documented degrade-to-skip SUCCESS
  (artifacts still produced). Standing up self-hosted DT is an operator infra
  step, out of this PR's scope.

## Status and sequencing

Both contexts are **PRODUCER-ONLY**: not in branch protection until PASS-A-c,
after observed green on live PRs (STEP1→…→STEP4 pattern). STEP9
(Pact/schemathesis consumer contract tests) builds on the same baseline and
registry. All actions SHA-pinned (semgrep mutable-tag policy).

## Rollback

Revert the PR — workflows, script, map keys and canon disappear; baseline file
untouched; artifacts expire in 14 days. *Singleton ledger-PR; shard
`passA-contracts-sbom`; I-24 append-only; ADR-117 emi-stack scope.*
