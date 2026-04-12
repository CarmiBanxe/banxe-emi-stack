---
name: Project: Starter Kit (IL-SK-01)
description: Merged developer Starter Kit — .claude/rules, .claude/commands, .claude/specs, .semgrep, GitHub Actions, PR/issue templates
type: project
---

# IL-SK-01 — Starter Kit Merge

**Status:** DONE ✅
**Коммит:** d39d709
**Описание:** `feat(governance): merge Starter Kit — rules, commands, specs, GH Actions, templates [IL-SK-01]`

## Что добавлено

### .claude/rules/ (16 правил)
Полный набор правил для Claude Code агентов:
- `00-global.md` — Conservative в regulated paths, read-before-edit
- `10-backend-python.md` — Protocol DI, Decimal, async-first, structured errors
- `20-api-contracts.md` — Backward compat, idempotency, X-Request-ID
- `30-testing.md` — InMemory stubs, ≥80% coverage, negative tests
- `40-docs.md` — Doc update triggers, ADR format
- `50-frontend.md` — React/Biome/Mitosis rules *(добавлен в IL-RETRO-02)*
- `60-migrations.md` — Additive-first, rollback required, locking risks
- `70-mcp-tools.md` — FastMCP patterns, audit trail *(добавлен в IL-RETRO-02)*
- `80-ai-agents.md` — Soul files, swarm, HITL *(добавлен в IL-RETRO-02)*
- `90-reporting.md` — UTC, reproducibility, lineage
- `95-incidents.md` — Investigate before patch, HITL for destructive
- `agent-authority.md` — L1-L4 autonomy matrix
- `compliance-boundaries.md` — Domain separation
- `financial-invariants.md` — I-01..I-28 registry
- `git-workflow.md` — Branch policy, commit format, pre-commit requirements
- `quality-gates.md` — 6 gates: Ruff, Ruff format, Semgrep, pytest, Biome, LucidShark
- `security-policy.md` — 10 Semgrep rules, sanctioned jurisdictions
- `session-continuity.md` — New session template, QRAA protocol

### .claude/commands/ 
Slash commands для типовых задач (recon-status, quality-gate, etc.)

### .claude/specs/
Templates:
- `bug-spec-template.md`
- `feature-spec-template.md`
- `incident-template.md`
- `migration-spec-template.md`
- `risk-assessment-template.md`

### .semgrep/banxe-rules.yml
10 custom security rules:
- `banxe-hardcoded-secret` (ERROR)
- `banxe-sql-injection-python` (ERROR)
- `banxe-sql-injection-javascript` (ERROR)
- `banxe-unsafe-eval` (ERROR)
- `banxe-float-money` (ERROR) — enforces I-01
- `banxe-log-pii` (WARNING)
- `banxe-no-plain-password` (ERROR)
- `banxe-shell-injection` (ERROR)
- `banxe-audit-delete` (ERROR) — enforces I-24
- `banxe-clickhouse-ttl-reduce` (ERROR) — enforces I-08

### .github/
- `workflows/quality-gate.yml` — 5 parallel jobs
- `workflows/lint-python.yml` — ruff + semgrep
- `workflows/lint-frontend.yml` — biome + vitest
- `PULL_REQUEST_TEMPLATE.md`
- `ISSUE_TEMPLATE/`

### .pre-commit-config.yaml
- astral-sh/ruff-pre-commit@v0.11.6 (ruff + ruff-format)
- Biome local hook (frontend)
- Semgrep banxe-rules
- Pytest fast (--override-ini=addopts=)

## **Why:** Без Starter Kit агенты не имели consistent правил. После merge — единый набор правил применяется ко всем IL.
## **How to apply:** При старте нового IL — проверить .claude/rules/ на покрытие новой фичи.
