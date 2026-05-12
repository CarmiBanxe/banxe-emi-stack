# Operator runbook — S16.5 G-CI-02 branch-protection activation

Owner sprint: S16.5.
Anchors: ADR-035 G-CI-02; ADR-035 Step 3 baseline (`.github/protection-update.json`);
S16.5 PREP package files (`.github/protection-update-v2.json`,
`scripts/validate-g-ci-02-prep.sh`, this runbook).
Status: PREP (this PR delivers the package only; **no remote API mutation here**).

---

## Purpose

Switch branch protection on `main` of `CarmiBanxe/banxe-emi-stack` to require
all currently-mandatory CI gates as `required_status_checks`. Today's
protection state requires only 3 of those gates (the baseline shipped by
ADR-035 Step 3); the v2 manifest in this package adds 8 more discovered in
`.github/workflows/*.yml`.

## Non-goal

**This PR does NOT mutate the live protection state.** All artefacts are
inert until an operator with `admin` on the repository runs the activation
command in §3 below, gated by §6 HITL. Sub-B is single-writer-restricted
per §71 of project canon and cannot execute this change.

## 1. Pre-flight (operator on a developer host)

1. Confirm working directory at the repo root with the v2 manifest:
   `ls .github/protection-update-v2.json`.
2. Run the offline validator and confirm `Summary: N PASS / 0 FAIL`:
   ```sh
   bash scripts/validate-g-ci-02-prep.sh
   ```
3. Snapshot the current protection state for rollback:
   ```sh
   gh api repos/CarmiBanxe/banxe-emi-stack/branches/main/protection \
       > /tmp/protection-snapshot-$(date -u +%Y%m%dT%H%M%SZ).json
   ```
4. Inspect the snapshot — verify the `required_status_checks.contexts`
   array matches the documented baseline (3 entries on 2026-05-12).
5. Confirm GitHub App `guardian-*` checks are present in the snapshot
   (these are externally provided and preserved by the v2 manifest).
6. Verify the operator's GitHub session has the `admin:repo` scope:
   `gh auth status`.

## 2. Required status checks in v2

The 11 contexts in `.github/protection-update-v2.json` are:

| Context                              | Source                                | Status        |
|--------------------------------------|---------------------------------------|---------------|
| `guardian-factory`                   | external GitHub App                   | preserved     |
| `guardian-project`                   | external GitHub App                   | preserved     |
| `Smoke Gate (mock tier)`             | `.github/workflows/smoke-gate-mock.yml` | preserved   |
| `Smoke Gate (real stack)`            | `.github/workflows/smoke-gate-full.yml` | new (S16.5) |
| `Gitleaks - Secrets Scan`            | `.github/workflows/quality-gate.yml`  | new (S16.5)   |
| `Ruff lint + format`                 | `.github/workflows/quality-gate.yml`  | new (S16.5)   |
| `Biome lint + format (Frontend)`     | `.github/workflows/quality-gate.yml`  | new (S16.5)   |
| `Pytest (coverage >= 80%)`           | `.github/workflows/quality-gate.yml`  | new (S16.5)   |
| `Semgrep (banxe-rules)`              | `.github/workflows/quality-gate.yml`  | new (S16.5)   |
| `Vitest (frontend)`                  | `.github/workflows/quality-gate.yml`  | new (S16.5)   |
| `Alembic — schema drift check`       | `.github/workflows/alembic-check.yml` | new (S16.5)   |

All other protection toggles preserve the current live state: `strict=true`,
`enforce_admins=false`, `required_pull_request_reviews=null`,
`restrictions=null`.

## 3. Activation (operator-only, gated by §6 HITL)

Run from the repo root after §1 pre-flight passes:

```sh
gh api -X PUT repos/CarmiBanxe/banxe-emi-stack/branches/main/protection \
    --input .github/protection-update-v2.json
```

`gh api` will refuse if the operator lacks `admin:repo`. On success, GitHub
returns the new protection state. Capture the response for the audit trail:

```sh
gh api -X PUT repos/CarmiBanxe/banxe-emi-stack/branches/main/protection \
    --input .github/protection-update-v2.json \
    > /tmp/protection-after-$(date -u +%Y%m%dT%H%M%SZ).json
```

## 4. Post-flight verification

1. Re-read protection and confirm the 11-context list:
   ```sh
   gh api repos/CarmiBanxe/banxe-emi-stack/branches/main/protection \
       | jq -r '.required_status_checks.checks[].context'
   ```
2. Open a dry-run PR from a branch that intentionally fails one of the new
   gates (e.g. a deliberate lint violation). Verify the PR is `blocked`
   in the GitHub UI and that the failing check appears under
   `Required` in the status panel.
3. Close the dry-run PR without merging.
4. Record the dry-run PR number + outcome in the operator-side ledger
   against this runbook.

## 5. Rollback

If §4 reveals an unintended consequence (e.g. a previously-optional check
is now blocking legitimate work, or a gate name was misspelled), roll back
in this exact order:

1. Re-apply the snapshot captured in §1 step 3:
   ```sh
   gh api -X PUT repos/CarmiBanxe/banxe-emi-stack/branches/main/protection \
       --input /tmp/protection-snapshot-<TIMESTAMP>.json
   ```
2. Verify the rollback took effect:
   ```sh
   gh api repos/CarmiBanxe/banxe-emi-stack/branches/main/protection \
       | jq -r '.required_status_checks.checks[].context'
   ```
3. Confirm the dry-run PR is no longer `blocked` for the previously-new
   reasons (close it once verified).
4. File a follow-up task: name the specific contexts that misbehaved, and
   propose a v3 manifest that excludes them OR fixes the underlying CI
   issue first.

## 6. HITL gate

This activation requires:

- **Central approval** — confirms the v2 manifest matches the discovered
  CI surface AND that none of the listed gates is flapping today.
- **Operator approval** — confirms there is no in-flight merge train that
  would be blocked unexpectedly by the new gates within the next 24 h.

Both approvals are recorded against this runbook in the operator-side
sign-off ledger before the §3 activation command is executed.

## 7. Operator sign-off block

```
Activation date     : __________________________
Executor            : __________________________
Central             : __________________________ (approval)
Operator            : __________________________ (approval)
Snapshot file       : /tmp/protection-snapshot-_________________.json
Activation response : /tmp/protection-after-______________________.json
Dry-run PR          : #_____ (result: BLOCKED as expected / UNEXPECTED)
Outcome             : [ ] PASS    [ ] FAIL    [ ] ROLLBACK
Rollback notes      :


```

## 8. References

- `.github/protection-update.json` — ADR-035 Step 3 baseline (3 contexts).
- `.github/protection-update-v2.json` — S16.5 G-CI-02 v2 (11 contexts).
- `scripts/validate-g-ci-02-prep.sh` — offline validator.
- `tests/unit/ci/test_g_ci_02_prep.py` — unit tests of the prep contract.
- `.github/ADR-035-STEP-3-OPERATOR.md` — earlier ADR-035 operator note.
