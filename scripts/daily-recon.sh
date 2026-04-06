#!/usr/bin/env bash
# daily-recon.sh — P0 CASS 7.15 daily safeguarding reconciliation
# Runs at 07:00 UTC Mon-Fri via cron
# FCA CASS 7.15 | banxe-emi-stack

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="/var/log/banxe"
RECON_DATE="${1:-$(date -u +%Y-%m-%d)}"

mkdir -p "$LOG_DIR"
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] daily-recon START date=$RECON_DATE"

# Load env
if [[ -f "$REPO_DIR/.env" ]]; then
    set -a
    source "$REPO_DIR/.env"
    set +a
fi

# Run reconciliation engine
cd "$REPO_DIR"
python3 -c "
import asyncio
import sys
from datetime import date
from decimal import Decimal

sys.path.insert(0, '.')

from services.recon.reconciliation_engine import ReconciliationEngine
from services.recon.statement_fetcher import StatementFetcher

# Minimal run — requires real LedgerPort + ClickHouse in production
# In Phase 0 (skeleton), validates imports only
print('ReconciliationEngine import OK')
print('StatementFetcher import OK')
print('RECON_DATE:', '${RECON_DATE}')
"

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] daily-recon DONE date=$RECON_DATE"
