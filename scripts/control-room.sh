#!/usr/bin/env bash
# Banxe Control-Room launcher — READ-ONLY observability surface.
# Canon: ADR-056 (Accepted) + INV-OPS-01. Runbook: docs/runbooks/CONTROL-ROOM.md.
#
# BOUNDARY (binding):
#   - MUST run as a NON-PRIVILEGED user: no docker group, no engine/DB credentials,
#     no write-scoped tokens, no midaz access, no client-instruction path.
#   - Every pane below is READ-ONLY: watch/curl GET/echo only.
#     NO docker up/down/exec/restart, NO psql/DB writes, NO POST/PUT/DELETE. EVER.
#   - herdr stays multiplexer-only: socket API OFF, plugins OFF.
#   - engine-services pane observes via HTTP-health/TCP only (V1, operator-ratified):
#     NO docker socket, NO credentials. Degradation rule: if a datastore check
#     demands auth, fall back to TCP reachability
#     (`timeout 2 bash -c "</dev/tcp/localhost/PORT"`); NEVER put credentials
#     in the Control-Room environment to "fix" a pane.
#
# Idempotent: exits 0 if the Control-Room tmux session already exists.
set -euo pipefail

SESSION=banxe-controlroom
HERDR="${HERDR_BIN:-$HOME/.local/bin/herdr}"   # prod: systemd sets HERDR_BIN=/opt/banxe/control-room/herdr
TMUX=/usr/bin/tmux

if "$TMUX" has-session -t "$SESSION" 2>/dev/null; then
  exit 0
fi

# tmux provides the PTY; herdr runs inside as the persistent inner session.
"$TMUX" new-session -d -s "$SESSION" -x 220 -y 50 "$HERDR --session banxe-controlroom-inner"
sleep 4

# helper: send herdr prefix sequence / literal text into the wrapper pane
hk()  { "$TMUX" send-keys -t "$SESSION" C-b "$@"; sleep 1.5; }
lit() { "$TMUX" send-keys -t "$SESSION" -l "$1"; sleep 0.5; "$TMUX" send-keys -t "$SESSION" Enter; sleep 1; }
ren() { hk P; sleep 0.5; lit "$1"; }

# fresh tab for the Control-Room layout
hk c

# p1 gateway-health (initial pane)
ren "gateway-health"
lit "watch -n5 'curl -s -o /dev/null -w \"gateway=%{http_code}\\n\" http://127.0.0.1:4000/health/liveliness'"

# p2 engine-services (vertical split) — HTTP-health/TCP read-only (no docker socket, no creds)
hk v
ren "engine-services"
P2_CMD=$(cat <<'EOF'
watch -n10 '
for s in \
  "gateway      http://127.0.0.1:4000/health/liveliness" \
  "banxe-api    http://localhost:8000/health" \
  "txn-monitor  http://localhost:8000/v1/monitor/health" \
  "marble-aml   http://localhost:3000/health" \
  "grafana      http://localhost:3001/api/health" \
  "superset     http://localhost:8088/health" \
  "mock-aspsp   http://localhost:8888/actuator/health"; do
  set -- $s
  printf "%-12s %s\n" "$1" "$(curl -fsS -o /dev/null -w "%{http_code}" -m 3 "$2" || echo DOWN)"
done
printf "%-12s %s\n" postgres   "$(pg_isready -h localhost -p 5432 -q && echo OK || echo DOWN)"
printf "%-12s %s\n" clickhouse "$(curl -fsS -m 3 "http://localhost:8123/?query=SELECT%201" 2>/dev/null || echo DOWN)"
printf "%-12s %s\n" redis      "$(redis-cli -h localhost -p 6379 ping 2>/dev/null || echo NOAUTH/DOWN)"
'
EOF
)
lit "$P2_CMD"

# p3 grafana/superset links (horizontal split in right column)
hk -- -
ren "grafana"
lit "echo 'Grafana (view-only): http://localhost:3000'; echo 'Superset: http://localhost:8088'"

# p4 transaction-monitor (another split right column)
hk -- -
ren "transaction-mon"
lit "echo 'runbook: docs/runbooks/transaction-monitor.md'; :"

# back to left column for p5/p6
hk h
# p5 recon-status
hk -- -
ren "recon-status"
lit "echo 'runbook: docs/runbooks/banxe-recon-service-activation.md'; :"

# p6 ops-readonly
hk -- -
ren "ops-readonly"
lit "echo 'READ-ONLY ops shell. NEVER run mutating/payment/db-write commands (see ADR-056 / CONTROL-ROOM.md)'"

exit 0
