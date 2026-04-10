#!/usr/bin/env bash
# post-edit-scan.sh — Post-edit LucidShark scan reminder/trigger
# Source: .claude/settings.json (PostToolUse hook), .claude/CLAUDE.md
# Created: 2026-04-10
# Migration Phase: 3
#
# Purpose: After code edits, remind or trigger a LucidShark scan.
# This mirrors the PostToolUse hook in .claude/settings.json which fires
# on Edit|Write|NotebookEdit events.
#
# Usage (standalone):
#   bash .claude/hooks/post-edit-scan.sh [file1 file2 ...]
#
# In Claude Code, the existing settings.json hook handles this automatically.
# This script is for manual invocation or CI integration.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_DIR"

FILES_CHANGED="${*:-}"

echo "=== Post-Edit Scan ==="

# ── Option 1: LucidShark MCP (preferred in Claude Code) ─────────────────────
# In Claude Code sessions, use MCP:
#   mcp__lucidshark__scan(fix=true)
# This script is for cases where MCP is not available.

# ── Option 2: LucidShark CLI ────────────────────────────────────────────────
if command -v lucidshark &>/dev/null; then
    echo "Running LucidShark scan..."
    if [[ -n "$FILES_CHANGED" ]]; then
        lucidshark scan --fix --format ai --files $FILES_CHANGED
    else
        lucidshark scan --fix --format ai
    fi
    echo "LucidShark scan complete"
else
    echo "[LucidShark] Code modified — scan before completing task"
    echo "  MCP: mcp__lucidshark__scan(fix=true)"
    echo "  CLI: lucidshark scan --fix --format ai"
    echo ""
    echo "LucidShark not found in PATH — install or use MCP tool in Claude Code"
fi

# ── Option 3: Ruff quick check (fallback) ───────────────────────────────────
if ! command -v lucidshark &>/dev/null; then
    echo ""
    echo "Fallback: running ruff check on changed files..."
    if [[ -n "$FILES_CHANGED" ]]; then
        ruff check $FILES_CHANGED 2>/dev/null || true
    else
        ruff check . 2>/dev/null || true
    fi
fi
