---
name: banxe-health
description: Load current BANXE project health before any task
context: fork
allowed-tools: Bash(make *), Bash(pytest *), Bash(ruff *), Bash(git *), Bash(docker *)
---

## BANXE Project Health Snapshot

- Branch: `!git branch --show-current`
- Last commit: `!git log --oneline -1`
- Dirty files: `!git status --short`
- Quality gate: `!make quality-gate 2>&1 | tail -5`
- Tests: `!pytest --tb=no -q 2>&1 | tail -3`
- Lint (Ruff): `!ruff check . --statistics 2>&1 | tail -3`
- Security (gitleaks): `!gitleaks detect --source . --no-banner 2>&1 | tail -3`
- Docker services: `!docker ps --format "table {{.Names}}\t{{.Status}}" 2>/dev/null | grep banxe || echo "No containers running"`
- Open IL items: `!grep -c "OPEN\|IN_PROGRESS" INSTRUCTION-LEDGER.md 2>/dev/null || echo "0"`

## Rules

- Before ANY code change, verify quality gate is green
- If tests are failing — fix them FIRST before new work
- If dirty files exist — commit or stash before new work
