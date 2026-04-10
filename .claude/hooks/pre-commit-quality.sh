#!/usr/bin/env bash
# pre-commit-quality.sh — Pre-commit quality gate for Claude Code sessions
# Source: .pre-commit-config.yaml, scripts/quality-gate.sh
# Created: 2026-04-10
# Migration Phase: 3
#
# Purpose: Runs the same checks as .pre-commit-config.yaml but as a standalone
# script that Claude Code hooks or manual invocations can call.
#
# Usage:
#   bash .claude/hooks/pre-commit-quality.sh
#
# Exit codes:
#   0 = all checks passed
#   1 = one or more checks failed

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_DIR"

FAILED=0

echo "=== Pre-commit Quality Gate ==="

# ── Step 1: Ruff lint ─────────────────────────────────────────────────────────
echo "[1/4] Ruff lint..."
if ruff check . 2>/dev/null; then
    echo "  ✓ Ruff lint passed"
else
    echo "  ✗ Ruff lint FAILED"
    FAILED=1
fi

# ── Step 2: Ruff format ──────────────────────────────────────────────────────
echo "[2/4] Ruff format check..."
if ruff format --check . 2>/dev/null; then
    echo "  ✓ Ruff format passed"
else
    echo "  ✗ Ruff format FAILED"
    FAILED=1
fi

# ── Step 3: Semgrep ──────────────────────────────────────────────────────────
echo "[3/4] Semgrep security scan..."
if command -v semgrep &>/dev/null; then
    if semgrep --config .semgrep/banxe-rules.yml --error --quiet 2>/dev/null; then
        echo "  ✓ Semgrep passed"
    else
        echo "  ✗ Semgrep FAILED"
        FAILED=1
    fi
else
    echo "  ⚠ Semgrep not installed — skipping"
fi

# ── Step 4: Pytest (fast) ────────────────────────────────────────────────────
echo "[4/4] Pytest (fast, no coverage)..."
if python3 -m pytest tests/ -x -q --timeout=30 --no-cov 2>/dev/null; then
    echo "  ✓ Pytest passed"
else
    echo "  ✗ Pytest FAILED"
    FAILED=1
fi

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
if [[ $FAILED -eq 0 ]]; then
    echo "=== ALL CHECKS PASSED — safe to commit ==="
    exit 0
else
    echo "=== CHECKS FAILED — fix before committing ==="
    exit 1
fi
