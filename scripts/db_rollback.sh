#!/usr/bin/env bash
# scripts/db_rollback.sh — Alembic rollback script
# S13-08 | banxe-emi-stack
#
# Usage:
#   bash scripts/db_rollback.sh              # roll back 1 step (default)
#   bash scripts/db_rollback.sh -n 2         # roll back N steps
#   bash scripts/db_rollback.sh --target abc1234  # roll back to specific revision
#   bash scripts/db_rollback.sh --status     # show current revision only
#
# Prerequisites:
#   - DATABASE_URL env var set (or defaults to banxe_dev.db)
#   - Python venv activated: source compliance/venv/bin/activate
#
# FCA CASS 15.12.4R: all schema changes must be audited and reversible.
# This script enforces that every rollback is logged with a timestamp.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_FILE="$REPO_ROOT/.ai/reports/alembic-rollback.log"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# ── Parse args ────────────────────────────────────────────────────────────────
STEPS=1
TARGET=""
STATUS_ONLY=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        -n|--steps)
            STEPS="$2"
            shift 2
            ;;
        --target)
            TARGET="$2"
            shift 2
            ;;
        --status)
            STATUS_ONLY=true
            shift
            ;;
        *)
            echo "Unknown argument: $1" >&2
            exit 1
            ;;
    esac
done

cd "$REPO_ROOT"

# ── Status only ───────────────────────────────────────────────────────────────
if [[ "$STATUS_ONLY" == "true" ]]; then
    echo "=== Alembic current revision ==="
    python -m alembic current
    echo ""
    echo "=== Alembic history (last 10) ==="
    python -m alembic history -r -10:head
    exit 0
fi

# ── Pre-rollback state ────────────────────────────────────────────────────────
BEFORE=$(python -m alembic current 2>&1 | tail -1)
echo "[$TIMESTAMP] Rollback initiated. Current revision: $BEFORE" | tee -a "$LOG_FILE"

# ── Safety prompt in interactive mode ─────────────────────────────────────────
if [[ -t 0 ]]; then
    if [[ -n "$TARGET" ]]; then
        echo "⚠️  Rolling back to revision: $TARGET"
    else
        echo "⚠️  Rolling back $STEPS step(s) from: $BEFORE"
    fi
    read -r -p "Confirm rollback? (yes/no): " CONFIRM
    if [[ "$CONFIRM" != "yes" ]]; then
        echo "Rollback cancelled."
        exit 0
    fi
fi

# ── Execute rollback ──────────────────────────────────────────────────────────
if [[ -n "$TARGET" ]]; then
    echo "Rolling back to revision: $TARGET"
    python -m alembic downgrade "$TARGET"
else
    DOWNGRADE_ARG="-${STEPS}"
    echo "Rolling back $STEPS step(s)..."
    python -m alembic downgrade "$DOWNGRADE_ARG"
fi

# ── Post-rollback state ───────────────────────────────────────────────────────
AFTER=$(python -m alembic current 2>&1 | tail -1)
echo "[$TIMESTAMP] Rollback complete. Revision: $BEFORE → $AFTER" | tee -a "$LOG_FILE"
echo ""
echo "✅ Rollback complete."
echo "   Before : $BEFORE"
echo "   After  : $AFTER"
echo ""
echo "To re-apply migrations: python -m alembic upgrade head"
echo "Rollback logged to: $LOG_FILE"
