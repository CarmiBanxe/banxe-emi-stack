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
| `ANTHROPIC_API_KEY` | external API | `claude-release-readiness.yml`, `claude-issue-triage.yml`, `claude-daily-report.yml` | **Not set** — workflows will fail if triggered; see §6 |

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

## 6. Open Issues

| # | Issue | Severity | Owner | Resolution |
|---|-------|----------|-------|------------|
| 1 | `ANTHROPIC_API_KEY` referenced in 3 workflows but **not set** in repo secrets | Medium | @mmber | Either set the secret in GitHub UI, or remove/disable the three workflows if not needed for this sandbox |

> **Note (sandbox context):** `banxe-emi-stack` is a sandbox environment.
> Workflows `claude-release-readiness.yml`, `claude-issue-triage.yml`, and
> `claude-daily-report.yml` reference `ANTHROPIC_API_KEY`. These will fail silently
> (or error) until the secret is set. Deferring to repo admin decision.

---

## 7. Ownership

| Scope | Owner |
|-------|-------|
| All secrets — both repos | @mmber |
| GitHub UI secret rotation | @mmber |
| Gitleaks configuration | @mmber (via `.github/workflows/`) |

---

## 8. Related

- IL-PROT-01: branch protection rules (CODEOWNERS, required checks)
- IL-REVW-01: removed `claude-pr-review.yml` (was referencing absent `ANTHROPIC_API_KEY`)
- Gitleaks workflow: `quality-gate.yml` → `Gitleaks - Secrets Scan` job
- CODEOWNERS: `/.github/workflows/ @mmber` — workflow changes require owner review
