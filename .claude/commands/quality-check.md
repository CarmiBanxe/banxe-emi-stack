# /quality-check — Run Full Quality Gate
# Source: scripts/quality-gate.sh, .pre-commit-config.yaml
# Created: 2026-04-10
# Migration Phase: 3

## Description

Run the complete quality gate: lint, format, security, and tests.
Use before committing or creating a PR.

## Steps

1. **Ruff lint:**
   ```bash
   ruff check .
   ```

2. **Ruff format check:**
   ```bash
   ruff format --check .
   ```

3. **Semgrep security scan:**
   ```bash
   semgrep --config .semgrep/banxe-rules.yml --error --quiet
   ```

4. **Pytest (fast, no coverage):**
   ```bash
   python -m pytest tests/ -x -q --timeout=30 --no-cov
   ```

5. **Pytest (full, with coverage):**
   ```bash
   python -m pytest tests/ -v --tb=short --cov=services --cov=api --cov-report=term-missing --cov-fail-under=80
   ```

6. **LucidShark (optional):**
   ```bash
   lucidshark scan --fix --format ai --all-files
   ```

## Full gate script

```bash
bash scripts/quality-gate.sh
```

## Pass criteria

- Ruff: zero issues
- Semgrep: zero errors
- Tests: all pass, coverage ≥ 80%
