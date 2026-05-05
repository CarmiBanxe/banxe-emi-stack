#!/usr/bin/env bash
# Guardian bash shim for Claude Code — pre-bash policy enforcement
# ADR-024 (canonical) | I-32..I-35 | banxe-emi-stack
#
# Reads command from stdin OR args, calls POST <GUARDIAN_BASE_URL>/audit,
# applies verdict per GUARDIAN_MODE.
#
# Env:
#   GUARDIAN_BASE_URL     default http://192.168.0.72:8195
#                         IP-form preferred: WSL2 DNS does not resolve evo1 hostname (see PR #47 D6).
#   GUARDIAN_MODE         enforce|audit|off (default: audit)
#   GUARDIAN_FAIL_MODE    open|closed (default: open in audit, closed in enforce)
#   GUARDIAN_TIMEOUT_S    default 5
#   GUARDIAN_SCOPE        default claude.bash
#   GUARDIAN_SUBJECT_TYPE default claude-code-session
#   GUARDIAN_SUBJECT_ID   default $(hostname)-$$ (operator can override)
#   GUARDIAN_ACTOR        default $USER
#
# Logs: ~/.claude/guardian-shim/audit.log (JSON-lines)
# Exit codes:
#   0  — verdict pass / warn (warn logged) / unknown (allowed, logged)
#   1  — verdict fail (blocked)
#   2  — Guardian unreachable AND fail-mode=closed
#   3  — internal shim error (jq/curl missing)

set -u
set -o pipefail

GUARDIAN_BASE_URL="${GUARDIAN_BASE_URL:-http://192.168.0.72:8195}"
GUARDIAN_MODE="${GUARDIAN_MODE:-audit}"
GUARDIAN_TIMEOUT_S="${GUARDIAN_TIMEOUT_S:-5}"
GUARDIAN_SCOPE="${GUARDIAN_SCOPE:-claude.bash}"
GUARDIAN_SUBJECT_TYPE="${GUARDIAN_SUBJECT_TYPE:-claude-code-session}"
GUARDIAN_SUBJECT_ID="${GUARDIAN_SUBJECT_ID:-$(hostname 2>/dev/null || echo unknown)-$$}"
GUARDIAN_ACTOR="${GUARDIAN_ACTOR:-${USER:-unknown}}"
GUARDIAN_FAIL_MODE="${GUARDIAN_FAIL_MODE:-}"
LOG_DIR="$HOME/.claude/guardian-shim"
LOG_FILE="$LOG_DIR/audit.log"

# Default fail-mode by mode
if [ -z "$GUARDIAN_FAIL_MODE" ]; then
  case "$GUARDIAN_MODE" in
    enforce) GUARDIAN_FAIL_MODE="closed" ;;
    *)       GUARDIAN_FAIL_MODE="open"   ;;
  esac
fi

mkdir -p "$LOG_DIR"

# OFF mode short-circuit
if [ "$GUARDIAN_MODE" = "off" ]; then
  echo "{\"ts\":\"$(date -u +%FT%TZ)\",\"mode\":\"off\",\"action\":\"bypass\"}" >> "$LOG_FILE"
  exit 0
fi

command -v curl >/dev/null 2>&1 || { echo "guardian-shim: curl missing" >&2; exit 3; }
command -v jq   >/dev/null 2>&1 || { echo "guardian-shim: jq missing"   >&2; exit 3; }

# Read command (prompt) from args or stdin
if [ "$#" -gt 0 ]; then
  PROMPT="$*"
else
  PROMPT="$(cat)"
fi

# Mask common secret patterns before POST
MASKED_PROMPT="$(printf '%s' "$PROMPT" | sed -E 's/(password|PASSWORD|secret|SECRET|api[_-]?key|API[_-]?KEY|access[_-]?token|refresh[_-]?token|client[_-]?secret)[^[:space:]]+/\1=***REDACTED***/g')"

REQUEST_ID="$(date -u +%s%N)-$$"

REQ_JSON=$(jq -n \
  --arg rid "$REQUEST_ID" \
  --arg st  "$GUARDIAN_SUBJECT_TYPE" \
  --arg sid "$GUARDIAN_SUBJECT_ID" \
  --arg sc  "$GUARDIAN_SCOPE" \
  --arg pr  "$MASKED_PROMPT" \
  --arg ac  "$GUARDIAN_ACTOR" \
  '{request_id:$rid, subject_type:$st, subject_id:$sid, scope:$sc, prompt:$pr, actor:$ac, dry_run:false, context:{shim_version:"0.1.0"}}')

RESP=$(curl -fsS --max-time "$GUARDIAN_TIMEOUT_S" -X POST \
  -H "Content-Type: application/json" \
  --data "$REQ_JSON" \
  "$GUARDIAN_BASE_URL/audit" 2>&1) || RESP=""

if [ -z "$RESP" ] || ! echo "$RESP" | jq -e .verdict >/dev/null 2>&1; then
  echo "{\"ts\":\"$(date -u +%FT%TZ)\",\"mode\":\"$GUARDIAN_MODE\",\"action\":\"unreachable\",\"fail_mode\":\"$GUARDIAN_FAIL_MODE\"}" >> "$LOG_FILE"
  if [ "$GUARDIAN_FAIL_MODE" = "closed" ]; then
    echo "guardian-shim: Guardian unreachable; fail-closed (enforce mode). Reasons: connect timeout or invalid response." >&2
    exit 2
  fi
  echo "guardian-shim: Guardian unreachable; fail-open (audit mode); proceeding." >&2
  exit 0
fi

RESULT=$(echo "$RESP" | jq -r '.verdict.result')
SUMMARY=$(echo "$RESP" | jq -r '.verdict.summary')
REASONS=$(echo "$RESP" | jq -c '.verdict.reasons')

# Log
echo "{\"ts\":\"$(date -u +%FT%TZ)\",\"mode\":\"$GUARDIAN_MODE\",\"result\":\"$RESULT\",\"summary\":\"$(printf '%s' "$SUMMARY" | sed 's/"/\\"/g')\",\"reasons\":$REASONS,\"request_id\":\"$REQUEST_ID\"}" >> "$LOG_FILE"

case "$RESULT" in
  pass)
    exit 0
    ;;
  warn)
    echo "guardian-shim: WARN — $SUMMARY" >&2
    [ "$REASONS" != "[]" ] && echo "guardian-shim: reasons: $REASONS" >&2
    exit 0
    ;;
  unknown)
    echo "guardian-shim: UNKNOWN verdict — $SUMMARY (proceeding)" >&2
    exit 0
    ;;
  fail)
    if [ "$GUARDIAN_MODE" = "enforce" ]; then
      echo "guardian-shim: BLOCKED — $SUMMARY" >&2
      echo "guardian-shim: reasons: $REASONS" >&2
      exit 1
    else
      echo "guardian-shim: FAIL verdict in audit mode — $SUMMARY (NOT blocking)" >&2
      echo "guardian-shim: reasons: $REASONS" >&2
      exit 0
    fi
    ;;
  *)
    echo "guardian-shim: unexpected verdict result='$RESULT'" >&2
    exit 0
    ;;
esac
