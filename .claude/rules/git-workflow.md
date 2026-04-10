# Git Workflow Rules — BANXE AI BANK
# Source: CLAUDE.md §5
# Created: 2026-04-10
# Migration Phase: 3
# Purpose: Enforce consistent git practices across the project

## Branch Policy

- `main` branch is protected — changes only through Pull Requests
- Feature branches: `feat/<scope>-<description>`
- Migration branches: `refactor/<description>`
- Hotfix branches: `fix/<description>`

## Commit Rules

- Each commit = one logical unit of work
- Commit message format: `feat(P0-FA-NN): description` (for P0 items)
- General format: `<type>(<scope>): <description>`
- Types: `feat`, `fix`, `refactor`, `docs`, `test`, `scaffold`, `chore`
- Instruction Ledger (IL) update is mandatory after each P0 step
- Co-author attribution for AI-assisted commits:
  `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>`

## Pre-Commit Requirements

Quality gate must pass before any commit:
1. `ruff check .` — lint (zero issues)
2. `ruff format --check .` — formatting
3. `semgrep --config .semgrep/banxe-rules.yml --error` — security rules
4. `pytest tests/ -x -q --timeout=30 --no-cov` — fast test pass

See: `.pre-commit-config.yaml`, `scripts/quality-gate.sh`

## References

- CI pipeline: `.github/workflows/quality-gate.yml`
- Pre-commit config: `.pre-commit-config.yaml`
- Quality report: `QUALITY.md`
