# Secrets & Access Posture — banxe-emi-stack

**IL:** IL-SEC-01 (Sprint 42)
**Effective:** 2026-04-27
**Owner:** @mmber

> Canonical reference for secrets inventory, classification, rotation policy, and OIDC
> migration roadmap across `banxe-emi-stack` and `banxe-architecture`.
> Secret **values** are never stored here. Only names, classification, and metadata.

---

## 1. Scope

| Repository | Covered |
|------------|---------|
| `CarmiBanxe/banxe-emi-stack` | ✅ Yes (primary) |
| `CarmiBanxe/banxe-architecture` | ✅ Yes (companion) |

Covers: GitHub Actions repository secrets, built-in tokens, OIDC candidates,
and references in `.github/workflows/`.

---

## 2. Current Secrets Inventory

### 2.1 banxe-emi-stack

| Secret Name | Classification | Workflows that reference it | Notes |
|-------------|----------------|-----------------------------|-------|
| `GITHUB_TOKEN` | built-in | all workflows | Auto-provisioned by GitHub; scoped to repo; rotates per job |
| `ANTHROPIC_API_KEY` | external API | `claude-release-readiness.yml`, `claude-issue-triage.yml`, `claude-daily-report.yml` | **Not set** — all three workflows fail when triggered; two trigger automatically (see §6) |

### 2.2 banxe-architecture

| Secret Name | Classification | Workflows that reference it | Notes |
|-------------|----------------|-----------------------------|-------|
| `GITHUB_TOKEN` | built-in | `ci.yml`, `docs.yml` | Auto-provisioned; no custom secrets in this repo |

---

## 3. Classification

| Class | Description | Examples |
|-------|-------------|---------|
| `built-in` | Auto-provisioned by GitHub per-job; cannot be rotated manually | `GITHUB_TOKEN` |
| `external-api` | Third-party service credentials; subject to vendor key lifecycle | `ANTHROPIC_API_KEY` |
| `deploy` | Infrastructure deploy tokens (none currently configured) | _(reserved)_ |
| `observability` | Monitoring / alerting credentials (none currently configured) | _(reserved)_ |

---

## 4. Retention & Rotation Policy

| Class | Rotation cadence | Trigger events |
|-------|-----------------|----------------|
| `built-in` | GitHub-managed (per-job TTL) | N/A |
| `external-api` | ≤ 90 days, or on personnel change | Key compromise, team offboarding |
| `deploy` | ≤ 90 days, or on infrastructure change | Provider rotation, personnel change |
| `observability` | ≤ 180 days | Vendor expiry, personnel change |

**Hard rules:**
- No secret values in source code — enforced by Gitleaks (`quality-gate.yml` + `ci.yml`).
- Rotation is performed exclusively via GitHub UI (Settings → Secrets) — no `gh secret set` in CLI.
- On any suspected leak: rotate immediately, open a security incident issue (private), notify @mmber.

---

## 5. OIDC Migration Candidates

| Secret | OIDC feasible? | Notes |
|--------|---------------|-------|
| `GITHUB_TOKEN` | N/A — already ephemeral | No action needed |
| `ANTHROPIC_API_KEY` | ❌ No | Anthropic does not support GitHub OIDC federation; long-lived key required |
| Future: Docker Hub push token | ✅ Yes | GitHub → Docker Hub OIDC supported; implement when Docker push workflows are added |
| Future: cloud deploy token | ✅ Yes | Render / Fly.io support OIDC; implement at IL-DEPLOY-01 |

---

## 6. Claude Workflow Inventory (category B — ANTHROPIC_API_KEY referenced, secret not set)

> `claude-pr-review.yml` has no legacy — it was removed in IL-REVW-01 (Sprint 42, sha dd027cb).
> No other `claude-pr-review` workflow exists in this repo.

The three remaining Claude workflows all reference `ANTHROPIC_API_KEY` and are classified as
**category B**: exist, secret absent, candidates for a separate follow-up IL in Sprint 43.
**Do NOT remove or re-enable any of these in IL-SEC-01.** They are documented here only.

| Workflow | Trigger | Fires automatically? | Impact of missing secret |
|----------|---------|---------------------|--------------------------|
| `claude-release-readiness.yml` | `workflow_dispatch` (manual, requires `release_version` input) | No | Fails only when manually triggered |
| `claude-issue-triage.yml` | `issues: [opened, labeled]` | **Yes** — on every new/labeled issue | Job errors on every issue event |
| `claude-daily-report.yml` | `schedule: 0 7 * * 1-5` (07:00 UTC Mon-Fri) + `workflow_dispatch` | **Yes** — every weekday | Job errors every weekday morning |

**Priority note:** `claude-issue-triage` and `claude-daily-report` produce automatic failures
on a recurring basis. `claude-release-readiness` is lower urgency (manual only).

---

## 7. Open Issues

| # | Issue | Severity | Owner | Resolution |
|---|-------|----------|-------|------------|
| 1 | `claude-issue-triage.yml` fires on every issue event but `ANTHROPIC_API_KEY` not set → automatic job failures | High | @mmber | Sprint 43: IL-CLAUDE-01 — decide set secret or disable workflow |
| 2 | `claude-daily-report.yml` fires every weekday at 07:00 UTC but `ANTHROPIC_API_KEY` not set → recurring daily failures | High | @mmber | Sprint 43: IL-CLAUDE-01 — same decision |
| 3 | `claude-release-readiness.yml` references `ANTHROPIC_API_KEY` (manual trigger only) | Low | @mmber | Sprint 43: IL-CLAUDE-01 — bundle with issues 1 & 2 |

> **Note (sandbox context):** `banxe-emi-stack` is a sandbox environment.
> Secret values are never set via CLI — all changes via GitHub UI only.

---

## 8. Ownership

| Scope | Owner |
|-------|-------|
| All secrets — both repos | @mmber |
| GitHub UI secret rotation | @mmber |
| Gitleaks configuration | @mmber (via `.github/workflows/`) |

---

## 9. Related

- IL-PROT-01: branch protection rules (CODEOWNERS, required checks)
- IL-REVW-01: removed `claude-pr-review.yml` (was referencing absent `ANTHROPIC_API_KEY`)
- Gitleaks workflow: `quality-gate.yml` → `Gitleaks - Secrets Scan` job
- CODEOWNERS: `/.github/workflows/ @mmber` — workflow changes require owner review
