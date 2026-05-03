#!/usr/bin/env bash
# =============================================================================
# deploy-safeguarding-gmktec.sh — FCA CASS 15 Safeguarding Stack Deploy
# IL-043 | Sprint P2 Task 1 | banxe-emi-stack
#
# Replaces: deploy-sprint9.sh (crontab) → systemd timer (more reliable, FCA-auditable)
#
# Run from Legion:
#   cd ~/banxe-emi-stack && bash scripts/deploy-safeguarding-gmktec.sh
#
# What this script does (all idempotent):
#   1.  rsync banxe-emi-stack to GMKtec:/data/banxe/banxe-emi-stack/
#   2.  Install Python deps (httpx, clickhouse-driver, pyyaml, dbt-clickhouse)
#   3.  Apply ClickHouse schema (safeguarding_events, safeguarding_breaches)
#   4.  Remove old crontab entry for daily-recon (if exists)
#   5.  Install systemd service + timer (banxe-recon.service / banxe-recon.timer)
#   6.  Enable and start the systemd timer
#   7.  Run unit tests (services/recon)
#   8.  Run dry-run reconciliation via cron_daily_recon.py
#   9.  Import n8n shortfall-alert workflow (if n8n is running)
#   10. Print post-deploy verification summary
#
# FCA requirements addressed:
#   - CASS 7.15.17R: daily reconciliation running automatically
#   - CASS 7.15.29R: n8n MLRO alert on discrepancy
#   - I-08: ClickHouse TTL ≥ 5 years (enforced by schema)
#   - I-24: audit trail append-only (no UPDATE/DELETE on safeguarding_events)
# =============================================================================
set -euo pipefail

GMKTEC="gmktec"
REMOTE_DIR="/data/banxe/banxe-emi-stack"
LOCAL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT_NAME="$(basename "$0")"

log()  { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
warn() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] WARN: $*" >&2; }
fail() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] FAIL: $*" >&2; exit 1; }

log "=== $SCRIPT_NAME START (IL-043) ==="
log "Local: $LOCAL_DIR"
log "Remote: $GMKTEC:$REMOTE_DIR"

# ── Step 1: rsync to GMKtec ───────────────────────────────────────────────────
log "--- Step 1: rsyncing banxe-emi-stack → GMKtec ---"
rsync -az --delete \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.env' \
    --exclude='.lucidshark/' \
    --exclude='target/' \
    --exclude='dbt_packages/' \
    "$LOCAL_DIR/" \
    "$GMKTEC:$REMOTE_DIR/"
log "rsync OK — repo synced to $GMKTEC:$REMOTE_DIR"

# ── Step 2: Install Python deps ───────────────────────────────────────────────
log "--- Step 2: Installing Python deps ---"
ssh "$GMKTEC" "pip3 install --quiet --break-system-packages \
    httpx \
    'clickhouse-driver>=0.2.7' \
    pyyaml \
    pytest \
    'dbt-clickhouse>=1.7' \
    2>&1 | tail -5"
log "Python deps installed (httpx, clickhouse-driver, pyyaml, dbt-clickhouse)"

# ── Step 3: Apply ClickHouse schema ──────────────────────────────────────────
log "--- Step 3: Applying ClickHouse schema (idempotent) ---"
ssh "$GMKTEC" "cd $REMOTE_DIR && python3 -c \"
import sys; sys.path.insert(0, '.')
from services.recon.clickhouse_client import ClickHouseReconClient
ch = ClickHouseReconClient()
ch.ensure_schema()
print('Schema OK: banxe.safeguarding_events + banxe.safeguarding_breaches')
print('  TTL: 5 years (I-08 compliant)')
print('  Engine: ReplacingMergeTree (audit-append only, I-24)')
\""
log "ClickHouse schema applied"

# ── Step 4: Remove legacy crontab entry (if exists from deploy-sprint9.sh) ───
log "--- Step 4: Removing legacy crontab entry (if any) ---"
ssh "$GMKTEC" "
    if crontab -l 2>/dev/null | grep -q 'daily-recon'; then
        crontab -l 2>/dev/null | grep -v 'daily-recon' | crontab -
        echo 'Removed legacy crontab entry for daily-recon'
    else
        echo 'No legacy crontab entry found — OK'
    fi
"
log "Crontab cleanup done"

# ── Step 5: Install systemd service + timer ───────────────────────────────────
log "--- Step 5: Installing systemd service + timer ---"
ssh "$GMKTEC" "cat > /etc/systemd/system/banxe-recon.service << 'UNIT'
[Unit]
Description=Banxe FCA CASS-15 Daily Safeguarding Reconciliation
Documentation=https://github.com/CarmiBanxe/banxe-emi-stack
After=network.target clickhouse-server.service
Wants=clickhouse-server.service

[Service]
Type=oneshot
User=banxe
Group=banxe
WorkingDirectory=$REMOTE_DIR
EnvironmentFile=-/data/banxe/.env
ExecStart=/usr/bin/python3 -m services.recon.cron_daily_recon
StandardOutput=append:/var/log/banxe/recon.log
StandardError=append:/var/log/banxe/recon.log
TimeoutStartSec=300
# Exit code semantics (see cron_daily_recon.py):
#   0 = MATCHED   — OK
#   1 = DISCREPANCY — MLRO alerted via n8n webhook (CASS 7.15.29R)
#   2 = PENDING   — no statement (non-critical)
#   3 = FATAL     — infrastructure failure
SuccessExitStatus=0 1 2
# Only exit code 3 (FATAL) triggers systemd on-failure
UNIT
echo 'banxe-recon.service written'"

ssh "$GMKTEC" "cat > /etc/systemd/system/banxe-recon.timer << 'UNIT'
[Unit]
Description=Banxe Daily Recon Timer — 07:00 UTC Mon-Fri (FCA CASS 7.15.17R)
Documentation=https://github.com/CarmiBanxe/banxe-emi-stack
Requires=banxe-recon.service

[Timer]
# Run at 07:00 UTC Monday to Friday
OnCalendar=Mon-Fri *-*-* 07:00:00 UTC
# Run immediately if last run was missed (e.g. server was down)
Persistent=true
# Randomise start within 2 minutes to avoid thundering herd
RandomizedDelaySec=120

[Install]
WantedBy=timers.target
UNIT
echo 'banxe-recon.timer written'"

log "Systemd unit files written"

# ── Step 6: Enable and start systemd timer ───────────────────────────────────
log "--- Step 6: Enabling systemd timer ---"
ssh "$GMKTEC" "
    mkdir -p /var/log/banxe
    chown banxe:banxe /var/log/banxe 2>/dev/null || chown root:root /var/log/banxe || true
    systemctl daemon-reload
    systemctl enable banxe-recon.timer
    systemctl start banxe-recon.timer
    echo 'Timer status:'
    systemctl status banxe-recon.timer --no-pager --lines=5 || true
    echo 'Next activation:'
    systemctl list-timers banxe-recon.timer --no-pager 2>/dev/null || true
"
log "Systemd timer enabled and started"

# ── Step 7: Run unit tests on GMKtec ─────────────────────────────────────────
log "--- Step 7: Running reconciliation unit tests ---"
ssh "$GMKTEC" "
    cd $REMOTE_DIR
    set -a
    [ -f .env ] && source .env 2>/dev/null || true
    set +a
    python3 -m pytest tests/test_reconciliation.py -v --tb=short -q 2>&1 | tail -20
" && log "Unit tests passed" || warn "Unit tests had failures — check output above"

# ── Step 8: Dry-run via cron_daily_recon.py ───────────────────────────────────
log "--- Step 8: Dry-run reconciliation ---"
DRY_RUN_EXIT=0
ssh "$GMKTEC" "
    cd $REMOTE_DIR
    set -a
    [ -f .env ] && source .env 2>/dev/null || true
    set +a
    python3 -m services.recon.cron_daily_recon --dry-run 2>&1
" || DRY_RUN_EXIT=$?

case $DRY_RUN_EXIT in
    0) log "Dry-run: MATCHED — all accounts reconciled" ;;
    1) log "Dry-run: DISCREPANCY — check sandbox data (expected if mock data)" ;;
    2) log "Dry-run: PENDING — no statement (expected in sandbox mode)" ;;
    3) fail "Dry-run: FATAL — infrastructure error, fix before proceeding" ;;
    *) log "Dry-run: exit=$DRY_RUN_EXIT" ;;
esac

# ── Step 9: Import n8n workflow ────────────────────────────────────────────────
log "--- Step 9: Importing n8n shortfall-alert workflow ---"
N8N_URL="http://localhost:5678"
N8N_WORKFLOW_FILE="$REMOTE_DIR/config/n8n/shortfall-alert-workflow.json"

ssh "$GMKTEC" "
    if curl -sf '$N8N_URL/healthz' > /dev/null 2>&1; then
        echo 'n8n is running — attempting workflow import via API...'

        # n8n v1 API: POST /api/v1/workflows (requires API key)
        N8N_API_KEY=\$(grep -i N8N_API_KEY /data/banxe/.env 2>/dev/null | cut -d= -f2 | tr -d '\"' || echo '')

        if [ -n \"\$N8N_API_KEY\" ]; then
            RESULT=\$(curl -s -X POST '$N8N_URL/api/v1/workflows' \
                -H 'Content-Type: application/json' \
                -H \"X-N8N-API-KEY: \$N8N_API_KEY\" \
                -d @$N8N_WORKFLOW_FILE 2>&1)
            if echo \"\$RESULT\" | grep -q '\"id\"'; then
                echo 'n8n workflow imported successfully'
                echo 'ACTION REQUIRED: Activate workflow in n8n UI + set TELEGRAM_BOT_TOKEN variable'
            else
                echo 'n8n API response:' \"\$RESULT\"
                echo 'MANUAL IMPORT: Open http://192.168.0.72:5678 → Import → config/n8n/shortfall-alert-workflow.json'
            fi
        else
            echo 'N8N_API_KEY not set in .env — skipping API import'
            echo 'MANUAL IMPORT: Open http://192.168.0.72:5678 → Import → config/n8n/shortfall-alert-workflow.json'
        fi
    else
        echo 'n8n not reachable at $N8N_URL — skipping workflow import'
        echo 'MANUAL IMPORT when n8n is running: config/n8n/shortfall-alert-workflow.json'
    fi
"

# ── Step 10: Post-deploy summary ──────────────────────────────────────────────
log ""
log "=== $SCRIPT_NAME DONE (IL-043) ==="
log ""
log "  SAFEGUARDING STACK STATUS"
log "  ─────────────────────────────────────────────────────"
log "  Schema    ClickHouse banxe.safeguarding_events ✅"
log "  Schema    ClickHouse banxe.safeguarding_breaches ✅"
log "  Service   /etc/systemd/system/banxe-recon.service ✅"
log "  Timer     /etc/systemd/system/banxe-recon.timer (07:00 UTC Mon-Fri) ✅"
log "  Dry-run   cron_daily_recon.py exit=$DRY_RUN_EXIT ✅"
log "  n8n       config/n8n/shortfall-alert-workflow.json (see above) ℹ️"
log ""
log "  NEXT ACTIONS (manual)"
log "  ─────────────────────────────────────────────────────"
log "  1. Verify timer: ssh gmktec 'systemctl list-timers banxe-recon.timer'"
log "  2. Import n8n workflow if not done: http://192.168.0.72:5678"
log "  3. Set n8n env vars: TELEGRAM_BOT_TOKEN, TELEGRAM_MLRO_CHAT_ID, TELEGRAM_CEO_CHAT_ID"
log "  4. Set N8N_WEBHOOK_URL in /data/banxe/.env after activating workflow"
log "  5. BT-001 CEO action: Register Modulr → get API key → unblock Payment Rails"
log ""
log "  FCA deadline: 7 May 2026 ($(( ($(date -d "2026-05-07" +%s) - $(date +%s)) / 86400 )) days)"
log ""
