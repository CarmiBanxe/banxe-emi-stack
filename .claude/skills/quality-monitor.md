---
name: quality-monitor
description: AI agent that monitors code quality tools effectiveness in banxe-emi-stack
user-invocable: true
disable-model-invocation: true
context: fork
---

# Quality Monitor Agent

## Purpose
Track and report effectiveness of all code quality tools in banxe-emi-stack.

## Quality Tools Registry

| Tool | Scope | Config | Workflow | Target |
|------|-------|--------|----------|--------|
| Biome | Frontend lint+format | frontend/biome.json | lint-frontend.yml | 0 errors |
| Vitest | Frontend tests | frontend/vitest.config.ts | lint-frontend.yml | 100% pass |
| Ruff | Python lint+format | ruff.toml | quality-gate.yml | 0 errors |
| Semgrep | Security SAST | .semgrep/banxe-rules.yml | quality-gate.yml | 0 findings |
| Gitleaks | Secrets scan | N/A | quality-gate.yml | 0 leaks |
| Pytest | Python tests+coverage | pytest.ini | quality-gate.yml | >=80% cov |
| mypy | Python type check | N/A | quality-gate.yml | 0 errors |
| Alembic | DB migrations | alembic.ini | alembic-check.yml | head valid |

## Health Check Procedure

When invoked, run this checklist:

1. **Workflow Status** - Check GitHub Actions for last run status of:
   - `quality-gate.yml` (main gate)
   - `lint-frontend.yml` (Biome + Vitest)
   - `lint-python.yml` (Ruff + Semgrep)
   - `alembic-check.yml` (migrations)
   - `claude-daily-report.yml` (Claude agent)
   - `claude-issue-triage.yml` (Claude agent)
   - `claude-pr-review.yml` (Claude agent)
   - `claude-release-readiness.yml` (Claude agent)

2. **Frontend Quality**
   - Run `cd frontend && npx biome lint .` -- expect 0 errors
   - Run `cd frontend && npm test` -- expect all pass
   - Check biome.json rules coverage

3. **Backend Quality**
   - Run `ruff check .` -- expect 0 errors
   - Run `pytest tests/ -v --cov` -- expect >=80%
   - Run `mypy src/` -- expect 0 errors
   - Run `semgrep --config .semgrep/banxe-rules.yml` -- expect 0

4. **Security**
   - Gitleaks scan clean
   - No hardcoded secrets in codebase
   - ANTHROPIC_API_KEY set in repo secrets

## Output Format

```
## Quality Gate Health Report
Date: YYYY-MM-DD

### Workflows
- quality-gate.yml: [PASS/FAIL] (last run: date)
- lint-frontend.yml: [PASS/FAIL]
- lint-python.yml: [PASS/FAIL]
- alembic-check.yml: [PASS/FAIL]
- claude-daily-report.yml: [PASS/FAIL]
- claude-issue-triage.yml: [PASS/FAIL]
- claude-pr-review.yml: [PASS/FAIL]
- claude-release-readiness.yml: [PASS/FAIL]

### Metrics
- Frontend: X errors, Y warnings
- Backend: X errors, Y warnings
- Test coverage: X%
- Security findings: X

### Status: GREEN / AMBER / RED
### Top 3 Actions:
1. ...
2. ...
3. ...
```

## Thresholds
- GREEN: All workflows pass, 0 errors, coverage >=80%
- AMBER: Warnings present OR coverage 60-80%
- RED: Any workflow failing OR errors present OR coverage <60%
