#!/usr/bin/env bash
# deploy-recon-stack.sh — IL-010: P0 deploy на GMKtec
# Запускать с Legion: cd ~/banxe-emi-stack && bash scripts/deploy-recon-stack.sh
# FCA CASS 7.15 | banxe-emi-stack

set -euo pipefail

GMKTEC="gmktec"
REMOTE_DIR="/data/banxe/banxe-emi-stack"
REPO_URL="https://github.com/CarmiBanxe/banxe-emi-stack.git"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

log "=== IL-010: P0 Recon Stack Deploy ==="

# ── STEP 1: Clone / pull repo on GMKtec ──────────────────────────────────────
log "STEP 1: Sync banxe-emi-stack on GMKtec..."
ssh "$GMKTEC" "
  if [ -d '$REMOTE_DIR/.git' ]; then
    cd '$REMOTE_DIR' && git pull --rebase
  else
    mkdir -p /data/banxe
    git clone '$REPO_URL' '$REMOTE_DIR'
  fi
  echo 'Repo OK: ' \$(cd '$REMOTE_DIR' && git log -1 --oneline)
"

# ── STEP 2: Copy .env (from GMKtec /data/banxe/.env if exists) ───────────────
log "STEP 2: Ensure .env on GMKtec..."
ssh "$GMKTEC" "
  if [ ! -f '$REMOTE_DIR/.env' ]; then
    if [ -f '/data/banxe/.env' ]; then
      cp /data/banxe/.env '$REMOTE_DIR/.env'
      echo '.env copied from /data/banxe/.env'
    else
      cp '$REMOTE_DIR/.env.example' '$REMOTE_DIR/.env'
      echo 'WARNING: .env copied from .env.example — fill in secrets!'
    fi
  else
    echo '.env already exists'
  fi
"

# ── STEP 3: Deploy Frankfurter (FA-06) ───────────────────────────────────────
log "STEP 3: Deploying Frankfurter FX rates (:8080)..."
ssh "$GMKTEC" "
  if docker ps --format '{{.Names}}' | grep -q '^banxe-frankfurter$'; then
    echo 'Frankfurter already running'
  else
    # Load env to get postgres credentials
    set -a; source '$REMOTE_DIR/.env' 2>/dev/null || true; set +a

    docker run -d \
      --name banxe-frankfurter \
      --restart unless-stopped \
      -p 8080:8080 \
      -e DATABASE_URL=\"postgres://\${POSTGRES_USER:-postgres}:\${POSTGRES_PASSWORD:-postgres}@localhost:5432/\${POSTGRES_DB:-banxe_compliance}\" \
      --network host \
      hakanensari/frankfurter:latest

    echo 'Frankfurter container started'
    sleep 5
  fi
"

# ── STEP 4: Smoke test Frankfurter ───────────────────────────────────────────
log "STEP 4: Smoke test Frankfurter..."
ssh "$GMKTEC" "
  for i in 1 2 3 4 5; do
    RESULT=\$(curl -sf 'http://localhost:8080/latest?from=GBP&to=EUR,USD' 2>/dev/null || echo '')
    if echo \"\$RESULT\" | grep -q '\"GBP\"'; then
      echo 'Frankfurter OK:' \$RESULT
      break
    fi
    echo 'Waiting for Frankfurter... ('\$i'/5)'
    sleep 5
  done
"

# ── STEP 5: pgAudit — install in existing postgres container (FA-04) ─────────
log "STEP 5: pgAudit setup on existing postgres:17..."
ssh "$GMKTEC" "
  # Check if pgaudit already installed
  INSTALLED=\$(docker exec postgres psql -U postgres -d banxe_compliance \
    -tAc \"SELECT extname FROM pg_extension WHERE extname='pgaudit';\" 2>/dev/null || echo '')

  if [ \"\$INSTALLED\" = 'pgaudit' ]; then
    echo 'pgAudit extension already installed'
  else
    echo 'Installing pgaudit package in postgres container...'
    docker exec postgres bash -c 'apt-get update -qq && apt-get install -y -qq postgresql-17-pgaudit'

    echo 'Enabling pgaudit in shared_preload_libraries...'
    docker exec postgres bash -c \"echo \\\"shared_preload_libraries = 'pgaudit'\\\" >> /var/lib/postgresql/data/postgresql.conf\"

    echo 'Restarting postgres container to load pgaudit...'
    docker restart postgres
    sleep 8

    echo 'Creating pgaudit extension...'
    docker exec postgres psql -U postgres -d banxe_compliance \
      -c \"CREATE EXTENSION IF NOT EXISTS pgaudit;\" \
      -c \"ALTER SYSTEM SET pgaudit.log = 'write, ddl';\" \
      -c \"ALTER SYSTEM SET pgaudit.log_relation = on;\" \
      -c \"SELECT pg_reload_conf();\"

    echo 'pgAudit configured'
  fi

  # Verify
  docker exec postgres psql -U postgres -d banxe_compliance \
    -c \"SELECT extname, extversion FROM pg_extension WHERE extname='pgaudit';\"
"

# ── STEP 6: Install Python deps + dry-run recon ──────────────────────────────
log "STEP 6: Python deps + daily-recon.sh dry-run..."
ssh "$GMKTEC" "
  cd '$REMOTE_DIR'
  pip3 install httpx --quiet 2>/dev/null || true
  bash scripts/daily-recon.sh
"

log "=== IL-010 DEPLOY DONE ==="
log "Summary:"
log "  Frankfurter: http://\$(hostname -f):8080/latest?from=GBP"
log "  pgAudit:     enabled on banxe_compliance"
log "  Recon:       daily-recon.sh dry-run complete"
