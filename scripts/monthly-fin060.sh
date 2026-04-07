#!/usr/bin/env bash
# monthly-fin060.sh — FCA FIN060a/b Monthly PDF Generator
# IL-015 Step 6 | FCA CASS 15 / PS25/12 | banxe-emi-stack
#
# Generates FIN060 safeguarding return PDF for the previous calendar month.
# Cron: 0 8 1 * * (1st of every month at 08:00 — deadline is 15th)
#
# Usage:
#   bash scripts/monthly-fin060.sh              # previous month (default)
#   bash scripts/monthly-fin060.sh 2026-03      # specific month YYYY-MM
#
# Exit codes:
#   0 = PDF generated and saved
#   1 = generation failed (check logs)
#   2 = clickhouse-driver not installed
#   3 = weasyprint not installed

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="/data/banxe/.env"
LOG_FILE="/data/banxe/logs/fin060-$(date +%Y%m).log"

# ── Load environment ──────────────────────────────────────────────────────────
if [[ -f "$ENV_FILE" ]]; then
    # shellcheck disable=SC1090
    set -a && source "$ENV_FILE" && set +a
fi

# ── Determine reporting period ────────────────────────────────────────────────
if [[ $# -ge 1 ]]; then
    PERIOD="$1"
    PERIOD_START="${PERIOD}-01"
    PERIOD_END=$(date -d "${PERIOD_START} +1 month -1 day" +%Y-%m-%d)
else
    # Default: previous calendar month
    PERIOD_START=$(date -d "$(date +%Y-%m-01) -1 month" +%Y-%m-%d)
    PERIOD_END=$(date -d "$(date +%Y-%m-01) -1 day" +%Y-%m-%d)
    PERIOD=$(date -d "$PERIOD_START" +%Y-%m)
fi

mkdir -p "$(dirname "$LOG_FILE")"
mkdir -p "${FIN060_OUTPUT_DIR:-/data/banxe/reports/fin060}"

echo "=== Banxe FIN060 Generator START | period=${PERIOD_START}..${PERIOD_END} ===" | tee -a "$LOG_FILE"
echo "Generated at: $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "$LOG_FILE"

cd "$REPO_DIR"

# ── Verify dependencies ───────────────────────────────────────────────────────
if ! python3 -c "import clickhouse_driver" 2>/dev/null; then
    echo "ERROR: clickhouse-driver not installed. Run: pip install clickhouse-driver" | tee -a "$LOG_FILE"
    exit 2
fi

if ! python3 -c "import weasyprint" 2>/dev/null; then
    echo "ERROR: weasyprint not installed. Run: pip install weasyprint" | tee -a "$LOG_FILE"
    exit 3
fi

# ── Generate PDF ──────────────────────────────────────────────────────────────
python3 - <<PYEOF 2>&1 | tee -a "$LOG_FILE"
import sys
from datetime import date
from services.reporting.fin060_generator import generate_fin060

try:
    period_start = date.fromisoformat("${PERIOD_START}")
    period_end = date.fromisoformat("${PERIOD_END}")
    pdf_path = generate_fin060(period_start, period_end)
    print(f"FIN060 PDF generated: {pdf_path}")
    print(f"FCA submission deadline: 15 {period_end.strftime('%B %Y')}")
except Exception as exc:
    print(f"ERROR: {exc}", file=sys.stderr)
    sys.exit(1)
PYEOF

GENERATE_EXIT=$?

if [[ $GENERATE_EXIT -ne 0 ]]; then
    echo "=== FIN060 FAILED (exit $GENERATE_EXIT) ===" | tee -a "$LOG_FILE"
    exit 1
fi

echo "=== FIN060 Generator END | SUCCESS ===" | tee -a "$LOG_FILE"
exit 0
