# GITNEXUS-REQUIRED-CHECK-PATHFILTER-FIX — always-report pattern (emi-stack)

> **STATUS: PROPOSED (singleton PR).** ⚠ SANDBOX.
> **Pointer-first (ADR-102):** the Fable 5 consultant response §3/§7 named this
> exact failure mode ("checks that never fire in the queue deadlock it").
> This note records the incident, the rule, and where it is applied.

## Incident (2026-07-28)

PASS-A-c made `contract-diff` + `sbom` REQUIRED while their workflow kept
`pull_request.paths:` filters. PR #337 (PASS B) touched none of those paths ⇒
the workflow never ran ⇒ the required contexts never reported ⇒ PR permanently
BLOCKED with everything else green. Systemic: every PR not touching
contract/SBOM paths would deadlock the same way.

## Rule (canon)

**A REQUIRED status context must ALWAYS report a conclusion on every PR.**
Path-filtering therefore moves INSIDE the job:

1. `pull_request.paths:` is removed from the workflow trigger;
2. a cheap pure-`git diff` relevance step (`id: rel`, no new actions) classifies
   the diff against the same path set;
3. heavy steps run `if: relevant == 'true'` — the gate is NOT weakened when
   relevant paths changed (full oasdiff / SBOM / index / build, NO-MOCK intact);
4. otherwise the job ends **COMPLETED/SUCCESS** with an explicit
   "no relevant changes" notice — never a missing context, never a skipped-job
   ambiguity.

## Applied to (the only path-filtered required producers)

| Workflow | Required contexts fixed |
|---|---|
| `.github/workflows/contracts-sbom.yml` | `contract-diff`, `sbom` (per-job relevance sets — sbom now reruns only on dependency changes, more precise than before) |
| `.github/workflows/scip-index.yml` | `scip-index` (matrix `index` jobs job-level-skip; aggregator always reports) |
| `.github/workflows/fleet-graph.yml` | `fleet-graph`, `impact-gate` |

Audited clean (no paths on pull_request): `codeowners-check.yml`,
`guardian.yml`, `main-serialize.yml`. `merge-queue-impact.yml` is
merge_group-only and not yet required (PASS-B-c must obey this rule when
requiring `mq-impact`).

## Self-unblocking property

This fix PR edits the three workflow files, and every relevance set includes
its own workflow file ⇒ all five contexts run FULL and report on the fix PR
itself. After merge, PR #337 needs only a rebase/update-branch for its contexts
to run and report (no-op or full per its diff).

## Rollback

Revert the PR — but note reverting REINTRODUCES the deadlock while the checks
stay required; the safe rollback order is: un-require the contexts first, then
revert. *Singleton ledger-PR; shard `fix-required-pathfilter-deadlock`; I-24.*
