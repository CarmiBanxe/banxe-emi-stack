#!/usr/bin/env bash
# deploy-psd2-gateway.sh — IL-011: adorsys PSD2 gateway deploy on GMKtec
# Запускать с Legion: cd ~/banxe-emi-stack && bash scripts/deploy-psd2-gateway.sh
# FCA CASS 7.15 FA-07 | banxe-emi-stack

set -euo pipefail

GMKTEC="gmktec"
REMOTE_DIR="/data/banxe/banxe-emi-stack"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

log "=== IL-011: adorsys PSD2 Gateway Deploy ==="

# ── STEP 1: Sync latest code ──────────────────────────────────────────────────
log "STEP 1: Sync banxe-emi-stack..."
rsync -a --exclude='.git' --exclude='.env' \
  /home/mmber/banxe-emi-stack/ "$GMKTEC:$REMOTE_DIR/"

# ── STEP 2: Check port availability ──────────────────────────────────────────
log "STEP 2: Checking ports 8888 and 8090..."
ssh "$GMKTEC" "
  for PORT in 8888 8090 5434; do
    if ss -tlnp | grep -q \":$PORT\"; then
      echo \"WARNING: Port $PORT already in use\"
    else
      echo \"Port $PORT: free\"
    fi
  done
"

# ── STEP 3: Start PSD2 stack ──────────────────────────────────────────────────
log "STEP 3: Starting docker-compose.psd2.yml..."
ssh "$GMKTEC" "
  cd '$REMOTE_DIR'
  set -a; [ -f .env ] && source .env; set +a
  docker compose -f docker/docker-compose.psd2.yml up -d
  echo 'Waiting 60s for Spring Boot startup...'
  sleep 60
"

# ── STEP 4: Health checks ────────────────────────────────────────────────────
log "STEP 4: Health checks..."
ssh "$GMKTEC" "
  echo 'psd2-postgres:'
  docker exec banxe-psd2-postgres pg_isready -U adorsys && echo 'OK' || echo 'FAIL'

  echo 'aspsp-mock:'
  curl -sf http://localhost:8090/actuator/health 2>/dev/null | head -c 100 || echo 'FAIL or starting'

  echo 'open-banking-gateway:'
  curl -sf http://localhost:8888/actuator/health 2>/dev/null | head -c 100 || echo 'FAIL or starting'

  echo 'Container states:'
  docker ps --filter name='banxe-psd2|banxe-aspsp' --format '{{.Names}}: {{.Status}}'
"

# ── STEP 5: Smoke test — list mock accounts ────────────────────────────────────
log "STEP 5: List mock accounts via gateway..."
ssh "$GMKTEC" "
  curl -sf 'http://localhost:8888/v1/accounts' \
    -H 'Accept: application/json' \
    -H 'X-Request-ID: banxe-smoke-test' \
    2>/dev/null | python3 -m json.tool 2>/dev/null | head -20 || echo 'Accounts endpoint not yet ready'
"

log "=== IL-011 DEPLOY DONE ==="
log "Gateway: http://gmktec:8888/actuator/health"
log "Mock bank: http://gmktec:8090/actuator/health"
log "Next: configure SAFEGUARDING_OPERATIONAL_IBAN + SAFEGUARDING_CLIENT_FUNDS_IBAN in .env"
