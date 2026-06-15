# ADR-035 Step 3 — Branch Protection Enforcement (Operator Note)

## Purpose

Add `Smoke Gate (mock tier)` as a **required status check** on the `main` branch.
After this, PRs cannot merge unless the mock smoke gate workflow passes.

## Dependency

**Step 2 (PR #101) must be merged first.** The workflow file
`.github/workflows/smoke-gate-mock.yml` must exist on `main` and have completed
at least one run so that GitHub recognizes the job name as a valid status check
context.

## Pre-flight checklist

1. Confirm PR #101 is merged:
   ```bash
   gh pr view 101 -R CarmiBanxe/banxe-emi-stack --json state -q .state
   # Expected: MERGED
   ```

2. Confirm the workflow has run at least once:
   ```bash
   gh run list -R CarmiBanxe/banxe-emi-stack -w "Smoke Gate — Mock Tier (ADR-035)" -L 1
   ```

3. Confirm current branch protection state:
   ```bash
   gh api repos/CarmiBanxe/banxe-emi-stack/branches/main/protection \
     --jq '.required_status_checks.checks[].context'
   ```

## Execute

**Review `.github/protection-update.json` before applying.** The JSON sets
`required_status_checks` with three checks: `guardian-factory`, `guardian-project`,
and `Smoke Gate (mock tier)`. Adjust if your current protection config has additional
checks or settings not captured in this file.

```bash
gh api repos/CarmiBanxe/banxe-emi-stack/branches/main/protection \
  --method PUT \
  --input .github/protection-update.json
```

## Post-flight verification

```bash
gh api repos/CarmiBanxe/banxe-emi-stack/branches/main/protection \
  --jq '.required_status_checks.checks[].context'
# Expected output includes:
#   guardian-factory
#   guardian-project
#   Smoke Gate (mock tier)
```

Open a test PR and confirm `Smoke Gate (mock tier)` appears as a required check.
