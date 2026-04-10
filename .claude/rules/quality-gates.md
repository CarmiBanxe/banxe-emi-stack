# Quality Gates — BANXE AI BANK
# Source: .pre-commit-config.yaml, .github/workflows/quality-gate.yml, QUALITY.md
# Created: 2026-04-10
# Migration Phase: 3
# Purpose: Define quality thresholds that must pass before merge

## Required Gates (all must PASS)

### Gate 1: Lint (Ruff)
```bash
ruff check .
```
- Zero issues required
- Config: `pyproject.toml` [tool.ruff]
- Line length: 100, target: Python 3.12
- Rules: E, F, I, W, UP (ignoring E501, UP042)

### Gate 2: Format (Ruff)
```bash
ruff format --check .
```

### Gate 3: Security (Semgrep)
```bash
semgrep --config .semgrep/banxe-rules.yml --error
```
- 10 custom BANXE rules (see `security-policy.md`)

### Gate 4: Tests (pytest)
```bash
python -m pytest tests/ -v --tb=short --cov=services --cov=api --cov-report=term-missing --cov-fail-under=80
```
- All tests must pass
- Coverage ≥ 80% on `services/` and `api/`
- Current: 995 tests green

### Gate 5: LucidShark (optional, post-edit)
```bash
lucidshark scan --fix --format ai
```
- Duplication detection, coverage analysis
- See: `.claude/skills/lucidshark/SKILL.md`

## Quality Report

- Latest report: `QUALITY.md`
- CI pipeline: `.github/workflows/quality-gate.yml`
- Local script: `scripts/quality-gate.sh`
- Pre-commit: `.pre-commit-config.yaml`
