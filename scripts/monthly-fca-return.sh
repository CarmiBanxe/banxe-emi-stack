#!/usr/bin/env bash
# monthly-fca-return.sh — P0 FIN060 → RegData submission
# Runs on 1st of each month at 06:00 UTC
# FCA CASS 15 | banxe-emi-stack

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="/var/log/banxe"

# Default: prior calendar month
REPORT_YEAR="${1:-$(date -u -d 'last month' +%Y)}"
REPORT_MONTH="${2:-$(date -u -d 'last month' +%m)}"

mkdir -p "$LOG_DIR"
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] monthly-fca-return START period=${REPORT_YEAR}-${REPORT_MONTH}"

# Load env
if [[ -f "$REPO_DIR/.env" ]]; then
    set -a
    source "$REPO_DIR/.env"
    set +a
fi

cd "$REPO_DIR"

# Step 1: Run dbt fin060 model
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Running dbt fin060_monthly..."
if command -v dbt &>/dev/null; then
    dbt run --select fin060_monthly --profiles-dir ./dbt --project-dir ./dbt
else
    echo "WARNING: dbt not found, skipping model run (install via: pip install dbt-clickhouse)"
fi

# Step 2: Generate FIN060 PDF
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Generating FIN060 PDF..."
python3 -c "
import sys
from datetime import date
import calendar

sys.path.insert(0, '.')
year = int('${REPORT_YEAR}')
month = int('${REPORT_MONTH}')
period_start = date(year, month, 1)
period_end = date(year, month, calendar.monthrange(year, month)[1])

try:
    from services.reporting.fin060_generator import generate_fin060
    pdf_path = generate_fin060(period_start, period_end)
    print(f'FIN060 PDF generated: {pdf_path}')
except Exception as e:
    print(f'ERROR generating FIN060: {e}')
    sys.exit(1)
"

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] monthly-fca-return DONE period=${REPORT_YEAR}-${REPORT_MONTH}"
echo "ACTION REQUIRED: Upload PDF to FCA RegData portal (CFO/MLRO sign-off required)"
