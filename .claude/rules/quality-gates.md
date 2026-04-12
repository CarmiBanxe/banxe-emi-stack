# Quality Gates — BANXE AI BANK
# Source: .pre-commit-config.yaml, .github/workflows/quality-gate.yml, QUALITY.md
# Created: 2026-04-10 | Updated: 2026-04-12 (IL-BIOME-01)
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
- **Active rule groups:** E, F, I, W, UP, B, SIM, ANN, S, DTZ, ERA
- Progressive adoption ignores tagged `→ IL-ANN-01 / IL-DTZ-01 / IL-B-01` in pyproject.toml
- `ANN101`/`ANN102` removed from Ruff — **do not add them to ignore list**
- Pre-commit: `astral-sh/ruff-pre-commit@v0.11.6`

**per-file-ignores:**

| Path | Suppressed |
|------|-----------|
| `tests/**/*.py` | S, ANN |
| `services/iam/**`, `services/providers/**` | S310 |
| `banxe_mcp/server.py` | S608 |
| `services/design_pipeline/**` | S602, S105 |
| `scripts/**`, `infra/**` | S |

### Gate 2: Format (Ruff)
```bash
ruff format --check .
```
- Pre-commit: `ruff-format` hook from `astral-sh/ruff-pre-commit@v0.11.6`

### Gate 3: Security (Semgrep)
```bash
semgrep --config .semgrep/banxe-rules.yml --error
```
- 10 custom BANXE rules (see `security-policy.md`)
- CI: SARIF output uploaded to GitHub Code Scanning (`lint-python.yml`)

### Gate 4: Tests (pytest)
```bash
python -m pytest tests/ -v --tb=short --cov=services --cov=api --cov-report=term-missing --cov-fail-under=80
```
- All tests must pass
- Coverage ≥ 80% on `services/` and `api/`
- Current: **1 931 tests** green (as of IL-BIOME-01 / IL-072)

### Gate 5: Frontend Lint (Biome — frontend only)
```bash
cd frontend && npx biome ci --reporter=github .
```
- Config: `frontend/biome.json`
- Replaces ESLint + Prettier (see `docs/adr/ADR-001-biome-vs-eslint.md`)
- **Excluded from Biome:** `src/generated/**` (Mitosis output), `**/*.lite.tsx` (Mitosis source)
- Pre-commit: local hook `biome-check-frontend` (files: `^frontend/`)
- CI: `biomejs/setup-biome@v2` in `lint-frontend.yml`

### Gate 6: LucidShark (optional, post-edit)
```bash
lucidshark scan --fix --format ai
```
- Duplication detection, coverage analysis
- See: `.claude/skills/lucidshark/SKILL.md`

---

## CI Pipeline — 5 Parallel Jobs

```
quality-gate.yml
├── ruff         (lint + format check)
├── biome        (frontend lint)
├── semgrep      (SAST)
├── test         (pytest) ← needs: ruff
└── vitest       (frontend tests) ← needs: biome
```

Dedicated per-language workflows:
- `.github/workflows/lint-python.yml` — triggered on `**.py` / `pyproject.toml`
- `.github/workflows/lint-frontend.yml` — triggered on `frontend/src/**`

---

## Makefile Targets

```bash
make quality-gate          # run all Python gates locally
make generate-component COMPONENT=Button
# Mitosis → React (src/generated/Button.tsx) → Biome auto-format
```

---

## Quality Report

- Latest report: `QUALITY.md`
- CI pipeline: `.github/workflows/quality-gate.yml`
- Local script: `scripts/quality-gate.sh`
- Pre-commit: `.pre-commit-config.yaml`
- ADR: `docs/adr/ADR-001-biome-vs-eslint.md`
