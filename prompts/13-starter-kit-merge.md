# PROMPT 13 — STARTER KIT MERGE
## For: Claude Code on Legion (BANXE AI BANK)
## Ticket: IL-SK-01 | Governance Layer
## Run AFTER: All implementation prompts (09-12) complete

---

## ROLE

You are a Senior DevOps & Governance Engineer for BANXE AI BANK.
Task: Merge the Banxe Claude Code Starter Kit governance layer into
the existing `banxe-emi-stack` repository WITHOUT overwriting any existing files.

## CRITICAL RULE

**NEVER overwrite or delete existing files.** Only ADD new files.
If a file already exists at the target path, SKIP it and log: "SKIP: [path] — already exists".

## CONTEXT

Working directory: `/home/mmber/banxe-emi-stack`
Branch: `refactor/claude-ai-scaffold`

### What already exists (DO NOT TOUCH):
- `.claude/rules/` — 8 files (agent-authority, compliance-b, financial-invari, git-workflow, infrastructure, quality-gates, security-polic, session-contin)
- `.claude/commands/` — 7 files (audit-export, daily-recon, deploy-check, mcp-status, monthly-fca-r, quality-check, recon-status)
- `.claude/hooks/`, `.claude/agents/`, `.claude/skills/`, `.claude/CLAUDE.md`, `.claude/settings.json`
- `.ai/registries/`, `.ai/reports/`, `.ai/soul.md`
- `.github/workflows/quality-gate.yml`
- `docs/API.md`, `docs/ARCHITECTURE-RECON.md`, `docs/ONBOARDING.md`, `docs/RUNBOOK.md`
- `CLAUDE.md` (root)
- All `services/`, `agents/`, `banxe_mcp/`, `prompts/`, `.semgrep/`, `infra/`, `dbt/`, `docker/`

---

## PHASE 1 — NUMBERED RULES (add missing domain rules)

Create these NEW files in `.claude/rules/` with numeric prefix for load order.
Do NOT touch existing rule files.

Create `.claude/rules/00-global.md`:
- Operating posture: conservative in regulated paths, correctness > speed
- Investigation protocol: read code before edits, quote files in plans
- Delivery protocol: reversible steps, small PR-sized patches
- Evidence protocol: facts vs assumptions, no inferred compliance
- Output discipline: scope, affected files, change summary, tests, risks

Create `.claude/rules/10-backend-python.md`:
- Explicit data flow, domain logic separate from framework
- No hidden global state, typed boundaries
- Fail loudly on invalid financial inputs
- No mixed refactor + behavior change
- Structured errors, never log secrets

Create `.claude/rules/20-api-contracts.md`:
- Backward compatibility unless approved migration
- Validate semantics not only shapes
- Idempotency for create/submit ops
- Traceability via request/correlation IDs
- Update API docs on any field/status change

Create `.claude/rules/30-testing.md`:
- Tests for changed business logic
- Targeted fast tests first
- Negative tests for payments, ledger, AML, auth
- Task not complete if tests missing without justification

Create `.claude/rules/40-docs.md`:
- Must update docs when changing: behavior, API, schemas, runbooks, controls, config
- Targets: docs/architecture, docs/compliance, docs/runbooks, docs/adr
- Style: what changed, why, risks, rollback

Create `.claude/rules/60-migrations.md`:
- Required sections: purpose, data affected, forward/rollback steps, compatibility, validation, blast radius
- Additive changes first, validate assumptions, call out locking risks

Create `.claude/rules/90-reporting.md`:
- Reproducibility, lineage, date ranges, timezone, cutoffs
- Source of truth per field, historical comparability

Create `.claude/rules/95-incidents.md`:
- Investigate before patching, facts vs hypotheses
- First output: fault domain, impact, timeline, evidence, mitigation, next step
- Never blindly: destructive cleanup, schema changes, mass reprocessing

### Verification:
- `ls .claude/rules/` shows 16+ files (8 existing + 8 new)
- No existing files modified

---

## PHASE 2 — UNIVERSAL SLASH COMMANDS (add missing)

Create these NEW files in `.claude/commands/`:

Create `.claude/commands/plan-feature.md`:
- Read-only mode first, do not modify files
- Output: Goal, business context, components, files to inspect, approach, risks, tests, docs, rollout/rollback
- Safety section if touches AML/KYC, ledger, reporting, auth, secrets, migrations

Create `.claude/commands/implement-ticket.md`:
- Use approved plan only, smallest safe slice, no scope widening
- Per slice: what changed, why, tests run, remaining risks, docs updated
- Stop and ask before destructive actions

Create `.claude/commands/review-pr.md`:
- Review for: correctness, security, regression, test sufficiency, docs, compliance/audit
- Classify: blocker, important, nice-to-have
- Each finding: severity, file path, problem, why it matters, fix direction

Create `.claude/commands/incident-analysis.md`:
- Do not patch immediately, investigate first
- Output: fault domain, symptoms, facts, unknowns, evidence, mitigation, hypotheses, next action

Create `.claude/commands/compliance-check.md`:
- Control/audit lens review
- Output: affected control, requirement source, decision points, evidence trail, explainability, gaps, approvals
- If requirement not in repo, say explicitly unverified

Create `.claude/commands/architecture-review.md`:
- Against Banxe architecture boundaries
- Output: components, coupling, data flow, failure modes, ops impact, security/compliance, ADR needed?

### Verification:
- `ls .claude/commands/` shows 13+ files (7 existing + 6 new)

---

## PHASE 3 — SPEC TEMPLATES (new directory)

Create `.claude/specs/` directory with 5 templates:

Create `.claude/specs/feature-spec-template.md`:
- Sections: Title, Business outcome, Problem, In/Out scope, Components affected, API/Data/Security/Compliance impact, Failure modes, Testing strategy, Rollout/Rollback plan, Docs updates, Open questions

Create `.claude/specs/bug-spec-template.md`:
- Sections: Title, Symptoms, Expected/Actual behavior, Impact, Domain, Reproduction steps, Evidence, Root cause hypothesis, Fix strategy, Tests required, Rollout notes

Create `.claude/specs/migration-spec-template.md`:
- Sections: Title, Reason, Data affected, Backward compatibility, Forward/Rollback steps, Validation checks, Downtime risk, Monitoring, Owner approvals

Create `.claude/specs/incident-template.md`:
- Sections: Title, Severity, Start time, Detection, Impact, Systems, Timeline, Facts, Hypotheses, Mitigations, Resolution, Follow-up, Runbook updates

Create `.claude/specs/risk-assessment-template.md`:
- Sections: Title, Domain, Risk summary, Worst-case, Likelihood, Impact, Existing/New controls, Test coverage, Monitoring, Rollback readiness, Approvals

### Verification:
- `ls .claude/specs/` shows 5 files

---

## PHASE 4 — GITHUB ACTIONS (Claude automation)

Create 4 NEW workflow files. Do NOT touch `quality-gate.yml`.

Create `.github/workflows/claude-pr-review.yml`:
- Trigger: pull_request (opened, synchronize, reopened)
- Uses: anthropics/claude-code-action@v1
- Prompt: Review for correctness, security, regression, tests, docs, compliance. Focus on ledger, AML/KYC, reporting, auth, secrets, webhooks, migrations. Classify: blocker/important/nice-to-have.
- claude_args: "--max-turns 5"

Create `.github/workflows/claude-issue-triage.yml`:
- Trigger: issues (opened, labeled)
- Prompt: Classify as bug/feature/compliance/security/infra/docs. Return: summary, domain, files to inspect, risks, tests required.

Create `.github/workflows/claude-daily-report.yml`:
- Trigger: schedule cron "0 7 * * 1-5"
- Prompt: Summarize recent activity. Include merged PRs, risky work, missing docs/tests, compliance/security/ledger impact.

Create `.github/workflows/claude-release-readiness.yml`:
- Trigger: workflow_dispatch
- Prompt: Assess readiness. Return: changes, risks, missing tests/docs, migration readiness, rollback readiness, go/no-go.

### Verification:
- `ls .github/workflows/` shows 5 files (1 existing + 4 new)

---

## PHASE 5 — ISSUE/PR TEMPLATES

Create `.github/ISSUE_TEMPLATE/` directory:

Create `.github/ISSUE_TEMPLATE/feature_request.md`:
- frontmatter: name "Feature request", about "Propose a new feature"
- Sections: Business outcome, Problem, Scope, Domains, Risks, Acceptance criteria, Compliance notes

Create `.github/ISSUE_TEMPLATE/bug_report.md`:
- frontmatter: name "Bug report", about "Report broken behavior"
- Sections: Expected/Actual, Reproduction, Impact, Domain, Logs, Risk level

Create `.github/ISSUE_TEMPLATE/compliance_change.md`:
- frontmatter: name "Compliance change", about "Control/policy/reporting change"
- Sections: Requirement source, Control impacted, Current/Desired behavior, Systems, Evidence, Approvals

Create `.github/PULL_REQUEST_TEMPLATE.md`:
- Sections: Summary, Why, Domains checklist (backend, api, aml/kyc, ledger, reporting, security, migrations, docs), Risks, Tests, Docs updated checklist, Rollout/rollback, Reviewer focus

### Verification:
- `ls .github/ISSUE_TEMPLATE/` shows 3 files
- `cat .github/PULL_REQUEST_TEMPLATE.md` exists

---

## PHASE 6 — DOCS STRUCTURE + MEMORY + SCRIPTS

Create docs subdirectories (if not exist):
- `docs/architecture/README.md` — architecture docs placeholder
- `docs/compliance/README.md` — compliance docs placeholder
- `docs/runbooks/README.md` — runbooks placeholder
- `docs/adr/README.md` — ADR placeholder

Create `.claude/memory/README.md`:
- Good for memory: task format, test sequence, naming conventions, review structure
- Bad for memory-only: regulatory requirements, ledger invariants, sanctions rules, secrets, production procedures

Create `scripts/bootstrap.sh`:
- mkdir -p all required directories
- echo "Bootstrap complete"

Create `scripts/validate-context.sh`:
- Check CLAUDE.md exists, .claude/rules exists, PR template exists
- Exit 1 on missing

Create `mcp/policy.md`:
- Principle: read-only first
- Allowed: docs lookup, ticket lookup, schema introspection, operational metadata
- Restricted: write to production, secret access, irreversible ops
- Requirement: every MCP server needs owner, scope, classification, approval

### Verification:
- All directories created
- Scripts executable: `chmod +x scripts/*.sh`

---

## PHASE 7 — GIT COMMIT

```bash
cd /home/mmber/banxe-emi-stack
git add -A
git commit -m "feat(governance): merge Starter Kit — rules, commands, specs, GH Actions, templates [IL-SK-01]"
git push
```

---

## INFRASTRUCTURE UTILIZATION CHECKLIST (CANON)

| # | Component | Used | Where |
|---|-----------|------|-------|
| 1 | Semgrep SAST | Existing | .semgrep/ |
| 2 | dbt models | Existing | dbt/ |
| 3 | n8n workflows | Existing | infra/n8n/ |
| 4 | Docker | Existing | docker/ |
| 5 | Grafana | Existing | infra/grafana/ |
| 6 | MCP tools | Existing | banxe_mcp/ |
| 7 | CLAUDE.md | Enhanced | Root + .claude/CLAUDE.md |
| 8 | .ai/registries | Existing | .ai/registries/ |
| 9 | Soul prompt | Existing | .ai/soul.md |
| 10 | GitHub Actions | NEW x4 | .github/workflows/ |
| 11 | Specs templates | NEW x5 | .claude/specs/ |
| 12 | Memory policy | NEW | .claude/memory/ |

---

## SUCCESS CRITERIA

- [ ] 8 new rule files in .claude/rules/ (numbered 00-95)
- [ ] 6 new command files in .claude/commands/
- [ ] 5 spec templates in .claude/specs/
- [ ] 4 GitHub Actions workflows (claude-*)
- [ ] 3 issue templates + 1 PR template
- [ ] docs/ subdirectories with READMEs
- [ ] Memory policy in .claude/memory/
- [ ] MCP policy in mcp/
- [ ] Scripts in scripts/
- [ ] NO existing files overwritten
- [ ] Clean commit with conventional format

---

*Created: 2026-04-11 by Perplexity Computer*
*For execution: `cat prompts/13-starter-kit-merge.md` then paste to Claude Code*
