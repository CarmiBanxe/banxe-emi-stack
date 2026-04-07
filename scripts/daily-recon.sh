#!/usr/bin/env bash
# =============================================================================
# daily-recon.sh — FCA CASS 7.15 Daily Safeguarding Reconciliation
# IL-013 Sprint 9 | banxe-emi-stack
#
# Schedule (cron on GMKtec):
#   0 7 * * 1-5 /data/banxe/banxe-emi-stack/scripts/daily-recon.sh >> /var/log/banxe/recon.log 2>&1
#
# Flow:
#   1. Load .env
#   2. Ensure ClickHouse schema (idempotent)
#   3. Poll CAMT.053 from mock-ASPSP (FA-07) if IBANs set
#   4. Run ReconciliationEngine via midaz_reconciliation.py
#   5. Write results to ClickHouse (banxe.safeguarding_events)
#   6. Exit code: 0=MATCHED, 1=DISCREPANCY, 2=PENDING, 3=FATAL
#
# FCA requirement: run daily, retain logs 5 years (I-15, CASS 7.15.17R)
# =============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="/var/log/banxe"
RECON_DATE="${1:-$(date -u +%Y-%m-%d)}"
DRY_RUN="${DRY_RUN:-0}"

# ── Setup ─────────────────────────────────────────────────────────────────────
mkdir -p "$LOG_DIR"
LOGFILE="$LOG_DIR/recon-${RECON_DATE}.log"

log() {
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" | tee -a "$LOGFILE"
}

log "=== daily-recon START | date=$RECON_DATE | dry_run=$DRY_RUN ==="

# ── Load environment ──────────────────────────────────────────────────────────
if [[ -f "$REPO_DIR/.env" ]]; then
    set -a
    source "$REPO_DIR/.env"
    set +a
    log "Loaded .env from $REPO_DIR"
else
    log "WARNING: .env not found — using system environment variables"
fi

# ── Sanity checks ─────────────────────────────────────────────────────────────
: "${MIDAZ_BASE_URL:?ERROR: MIDAZ_BASE_URL not set}"
: "${CLICKHOUSE_HOST:?ERROR: CLICKHOUSE_HOST not set}"
: "${STATEMENT_DIR:?ERROR: STATEMENT_DIR not set}"

mkdir -p "$STATEMENT_DIR"
log "Statement dir: $STATEMENT_DIR"

# ── Step 1: Ensure ClickHouse schema ─────────────────────────────────────────
log "Step 1: Ensuring ClickHouse schema..."
cd "$REPO_DIR"

python3 - <<'PYEOF'
import os
import sys
sys.path.insert(0, '.')
from services.recon.clickhouse_client import ClickHouseReconClient
try:
    ch = ClickHouseReconClient()
    ch.ensure_schema()
    print("ClickHouse schema OK")
except Exception as e:
    print(f"WARNING: ClickHouse schema ensure failed: {e}")
    sys.exit(0)  # non-fatal — may already exist
PYEOF

# ── Step 2: Poll CAMT.053 from mock-ASPSP (if IBANs configured) ──────────────
if [[ -n "${SAFEGUARDING_OPERATIONAL_IBAN:-}" ]] && [[ -n "${SAFEGUARDING_CLIENT_FUNDS_IBAN:-}" ]]; then
    log "Step 2: Polling CAMT.053 statements from mock-ASPSP ($ADORSYS_PSD2_URL)..."
    python3 - <<PYEOF
import sys
sys.path.insert(0, '.')
from services.recon.statement_poller import health_check, poll_statements
from datetime import date

if not health_check():
    print("WARNING: mock-ASPSP not reachable — will fall back to CSV if available")
    sys.exit(0)

recon_date = date.fromisoformat("${RECON_DATE}")
paths = poll_statements(recon_date)
print(f"Polled {len(paths)} CAMT.053 file(s):")
for p in paths:
    print(f"  {p}")
PYEOF
else
    log "Step 2: SAFEGUARDING IBANs not set — skipping CAMT.053 poll (sandbox mode)"
fi

# ── Step 3: Run ReconciliationEngine ─────────────────────────────────────────
log "Step 3: Running ReconciliationEngine..."

DRY_RUN_FLAG=""
if [[ "$DRY_RUN" == "1" ]]; then
    DRY_RUN_FLAG="--dry-run"
    log "  DRY RUN mode — no ClickHouse writes"
fi

set +e
python3 -m services.recon.midaz_reconciliation \
    --date "$RECON_DATE" \
    --json \
    $DRY_RUN_FLAG \
    2>&1 | tee -a "$LOGFILE"

RECON_EXIT=$?
set -e

# ── Step 4: Exit code interpretation ─────────────────────────────────────────
case $RECON_EXIT in
    0) log "=== daily-recon DONE: ALL MATCHED | date=$RECON_DATE ===" ;;
    1) log "=== daily-recon DONE: DISCREPANCY DETECTED | date=$RECON_DATE === (FCA CASS 7.15.29R: investigate within 1 business day)" ;;
    2) log "=== daily-recon DONE: PENDING (no statement) | date=$RECON_DATE ===" ;;
    3) log "=== daily-recon FATAL ERROR | date=$RECON_DATE ===" ; exit 3 ;;
    *) log "=== daily-recon unknown exit=$RECON_EXIT ===" ;;
esac

# Propagate meaningful exit codes (1=discrepancy, 2=pending alert cron monitor)
exit $RECON_EXIT
