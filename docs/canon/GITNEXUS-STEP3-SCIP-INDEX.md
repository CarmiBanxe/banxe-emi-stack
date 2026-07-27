# GITNEXUS-STEP3-SCIP-INDEX — symbol-graph producer (emi-stack only)

> **STATUS: PROPOSED (singleton PR).** ⚠ SANDBOX / TRAINING.
> **Pointer-first (ADR-102):** rationale = Fable 5 consultant response (GitNexus
> cross-repo control stack, §2 graph / §6 roadmap step 3); STEP1/1b/2 shards.
> This file records ONLY what STEP3 adds to **banxe-emi-stack**.

## What and why

SCIP (Sourcegraph Code Intelligence Protocol — the successor of LSIF, preferred per
Fable 5) indexes produce the **ground-truth symbol graph**: definitions, references,
cross-file usage. This is the substrate STEP4's fleet graph and impact gate consume.
Engine-neutral OSS protocol — no dependency on the PolyForm-NC GitNexus engine
(Fable 5 hard rule: GitNexus stays replaceable).

## Topology (7 targets, from `config/gitnexus/scip.targets.json`)

- **python (2):** repo root (`pyproject.toml`, covers all backend zones) and
  `services/safeguarding-engine` (own pyproject).
- **typescript (5):** `apps/banking-mobile`, `apps/banking-web`, `apps/mobile`,
  `apps/web`, `frontend` (each: tsconfig.json + package.json present).
- The target list is **generated** by `scripts/gitnexus/scip_manifest.py` from real
  manifests + `ownership.map.json` zones (join key = zone name; per-zone flag
  `scip_index`). Drift fails CI. Dirs with package.json but no tsconfig.json are
  recorded under `excluded` with the reason — exclusions are visible (NO-MOCK).
  Note: untracked dirs (e.g. local `external/`) are invisible to the committed
  tree and therefore correctly absent.

## Artifact contract (consumed by STEP4)

Per project per commit, artifact `scip-<slug>`:

| file | content |
|---|---|
| `index.scip` | SCIP index (absent when status=UNKNOWN) |
| `scip-meta.json` | `project, path, lang, graph_commit, built_at, indexer, status(OK/UNKNOWN), reason, scip_bytes` |

- **graph_commit** = the commit the graph describes (PR head SHA, not merge ref);
  **built_at** = index build time (UTC). Both mandatory — Fable 5 freshness rule:
  every graph artifact carries freshness metadata.
- **Freshness SLO (placeholder, activated at STEP4):** fleet graph must not lag
  main by more than N commits; consumers must surface `graph_commit` in verdicts.
- **NO-MOCK:** indexer failure ⇒ `status=UNKNOWN` + visible warning; a zero-byte
  index is never OK; all-projects-UNKNOWN fails the run (systemic).

## CI shape and cost

Producer workflow `.github/workflows/scip-index.yml`: manifest drift-check job →
matrix fan-out (7 jobs, `fail-fast: false`) → `scip-index` aggregate context.
Pinned indexers (verified on npm registry): `@sourcegraph/scip-python@0.6.6`,
`@sourcegraph/scip-typescript@0.4.0`. PR runs are path-filtered to code/manifest
changes and superseded commits cancel (cost control); main pushes always index.
Python deps are NOT installed for the root index (7 290 files — internal edges
resolve; external-package refs stay unresolved; revisit at STEP4 if needed).
TS uses `npm ci --ignore-scripts` (no arbitrary install scripts in CI).

**PRODUCER-ONLY:** `scip-index` must succeed as a workflow but is NOT in branch
protection. STEP3c (separate operator action, after observed green on live PRs)
decides requiring it — same STEP1→STEP1b→STEP1c pattern.

## Rollback

Revert the PR: workflows and manifests disappear; no state outside git and CI
artifacts (14-day retention). *Singleton ledger-PR; shard `step3-scip-index`;
I-24 append-only; ADR-117 emi-stack scope only.*
