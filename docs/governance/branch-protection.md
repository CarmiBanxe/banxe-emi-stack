# Branch Protection Policy — banxe-emi-stack

**IL:** IL-PROT-01 (Sprint 42)
**Effective:** 2026-04-27
**Configured via:** GitHub UI (Settings → Branches → Branch protection rules)

> This document is the canonical description of branch protection rules.
> The authoritative enforcement is in GitHub's branch protection settings.
> `gh api` is never used to configure these rules — all changes via GitHub UI only.

---

## Scope

| Branch | Protected |
|--------|-----------|
| `main` | ✅ Yes |
| `feat/*`, `fix/*`, `chore/*` | No (feature branches are ephemeral) |

---

## Required Pull Request Reviews

| Setting | Value |
|---------|-------|
| Minimum approvals required | 1 |
| Dismiss stale reviews on new push | Yes |
| Require review from CODEOWNERS | Yes (see `.github/CODEOWNERS`) |
| Restrict who can dismiss reviews | No additional restriction |

---

## Required Status Checks

All of the following checks must pass before merge is allowed:

| Check name | Workflow | Notes |
|------------|----------|-------|
| `Ruff lint + format` | `quality-gate.yml` | Python lint + format |
| `Biome lint + format (Frontend)` | `quality-gate.yml` | Frontend lint |
| `Semgrep (banxe-rules)` | `quality-gate.yml` | SAST / custom rules |
| `Gitleaks - Secrets Scan` | `quality-gate.yml` | Secrets detection |
| `Pytest (coverage >= 80%)` | `quality-gate.yml` | Test suite + coverage |
| `Vitest (frontend)` | `quality-gate.yml` | Frontend tests |
| `CodeRabbit` | External | AI code review |

> **Note:** `claude-review` workflow was removed in IL-REVW-01 (PR #13, commit `dd027cb`).
> It does not appear in required checks.

---

## Branch Restrictions

| Setting | Value |
|---------|-------|
| Allow force pushes | ❌ No |
| Allow branch deletions | ❌ No |
| Require linear history (squash-only) | ✅ Yes |
| Include administrators | ✅ Yes (admins not exempt) |

---

## CODEOWNERS

Defined in `.github/CODEOWNERS`. All paths owned by `@mmber`.
Critical paths with explicit ownership:

| Path | Owner |
|------|-------|
| `*` (all files) | `@mmber` |
| `/services/complaints/` | `@mmber` |
| `/services/fatca_crs/` | `@mmber` |
| `/services/customer_lifecycle/` | `@mmber` |
| `/services/client_statements/` | `@mmber` |
| `/.github/workflows/` | `@mmber` |
| `/.claude/` | `@mmber` |
| `/CLAUDE.md` | `@mmber` |

---

## Rationale

- Linear history ensures a clean, bisectable `git log` on `main`.
- Admin inclusion prevents privileged bypass of required checks.
- CODEOWNERS ensures the primary maintainer reviews all changes,
  especially in compliance-critical service paths.
- No `gh secret set` / `gh api` for protection rules — all changes
  are human-initiated via GitHub UI to maintain audit trail.

## Related

- IL-PROT-01: `banxe-architecture/instruction-ledger/sprint-42/IL-PROT-01-branch-protection-main.md`
- IL-REVW-01: removal of `claude-review` workflow (PR #13)
- IL-SEC-01: secrets posture review (Sprint 42)
- `.github/CODEOWNERS` (this repo)
