#!/usr/bin/env bash
# audit-export.sh — Annual audit trail export from ClickHouse
# Exports safeguarding_events for FCA / external auditor
# FCA CASS 15 | banxe-emi-stack

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXPORT_DIR="${AUDIT_EXPORT_DIR:-/data/banxe/exports/audit}"
YEAR="${1:-$(date -u +%Y)}"

mkdir -p "$EXPORT_DIR"
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] audit-export START year=$YEAR"

# Load env
if [[ -f "$REPO_DIR/.env" ]]; then
    set -a
    source "$REPO_DIR/.env"
    set +a
fi

OUTFILE="$EXPORT_DIR/safeguarding_events_${YEAR}.csv"

clickhouse-client \
    --host "${CLICKHOUSE_HOST:-localhost}" \
    --port "${CLICKHOUSE_PORT:-9000}" \
    --database "${CLICKHOUSE_DB:-banxe}" \
    --user "${CLICKHOUSE_USER:-default}" \
    --password "${CLICKHOUSE_PASSWORD:-}" \
    --query "
        SELECT *
        FROM banxe.safeguarding_events
        WHERE toYear(recon_date) = ${YEAR}
        ORDER BY recon_date, account_id
        FORMAT CSVWithNames
    " > "$OUTFILE"

ROWS=$(wc -l < "$OUTFILE")
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] audit-export DONE year=$YEAR rows=$ROWS file=$OUTFILE"
