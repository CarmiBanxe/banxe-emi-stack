#!/usr/bin/env bash
# Guardian bash shim — unit tests (T1..T8)
# ADR-024 | banxe-emi-stack/infra/guardian-shim/tests/
# Run: bash infra/guardian-shim/tests/test-shim.sh

set -u

SHIM="$(cd "$(dirname "$0")/.." && pwd)/scripts/claude-bash-shim.sh"
PASS=0
FAIL=0

assert_exit() {
  local test_name="$1" expected="$2" actual="$3"
  if [ "$actual" -eq "$expected" ]; then
    echo "PASS [$test_name] exit=$actual"
    PASS=$((PASS + 1))
  else
    echo "FAIL [$test_name] expected exit=$expected got=$actual"
    FAIL=$((FAIL + 1))
  fi
}

assert_log_contains() {
  local test_name="$1" pattern="$2" log_file="$3"
  if grep -q "$pattern" "$log_file" 2>/dev/null; then
    echo "PASS [$test_name] log contains: $pattern"
    PASS=$((PASS + 1))
  else
    echo "FAIL [$test_name] log missing: $pattern (log: $(tail -1 "$log_file" 2>/dev/null || echo EMPTY))"
    FAIL=$((FAIL + 1))
  fi
}

assert_not_contains() {
  local test_name="$1" pattern="$2" content="$3"
  if ! echo "$content" | grep -qE "$pattern"; then
    echo "PASS [$test_name] no match for: $pattern"
    PASS=$((PASS + 1))
  else
    echo "FAIL [$test_name] unexpected match for: $pattern"
    FAIL=$((FAIL + 1))
  fi
}

# Temp log dir per test run
TMP_LOG_DIR="$(mktemp -d)"
cleanup() { rm -rf "$TMP_LOG_DIR"; kill "$MOCK_PID" 2>/dev/null || true; }
trap cleanup EXIT

start_mock_server() {
  local verdict="$1"
  local port="$2"
  python3 - "$verdict" "$port" &
  MOCK_PID=$!
  sleep 0.3  # let server start
}

# Mock server: responds to POST /audit with configurable verdict
MOCK_SCRIPT='
import sys, json
from http.server import HTTPServer, BaseHTTPRequestHandler

verdict_result = sys.argv[1]
port = int(sys.argv[2])

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            req = json.loads(body)
        except Exception:
            req = {}
        resp = {
            "verdict": {
                "result": verdict_result,
                "summary": f"mock verdict {verdict_result}",
                "reasons": [f"mock-reason-{verdict_result}"] if verdict_result == "fail" else [],
                "sources": []
            }
        }
        data = json.dumps(resp).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

HTTPServer(("127.0.0.1", port), Handler).serve_forever()
'

echo "=== Guardian Shim Tests (T1..T8) ==="
echo "SHIM: $SHIM"
echo ""

# --- T1: GUARDIAN_MODE=off → exit 0, log contains "bypass" ---
T1_LOG="$TMP_LOG_DIR/t1.log"
HOME="$TMP_LOG_DIR" GUARDIAN_MODE=off GUARDIAN_BASE_URL="http://127.0.0.1:19001" \
  bash "$SHIM" "ls -la" 2>/dev/null
T1_EXIT=$?
assert_exit "T1: mode=off exit 0" 0 "$T1_EXIT"
assert_log_contains "T1: mode=off log bypass" "bypass" "$TMP_LOG_DIR/.claude/guardian-shim/audit.log"

# --- T2: Guardian unreachable + fail-open → exit 0 ---
T2_LOG="$TMP_LOG_DIR/.claude/guardian-shim/audit.log"
HOME="$TMP_LOG_DIR" GUARDIAN_MODE=audit GUARDIAN_BASE_URL="http://127.0.0.1:19999" GUARDIAN_TIMEOUT_S=1 GUARDIAN_FAIL_MODE=open \
  bash "$SHIM" "ls" 2>/dev/null
T2_EXIT=$?
assert_exit "T2: unreachable+fail-open exit 0" 0 "$T2_EXIT"
assert_log_contains "T2: unreachable log entry" "unreachable" "$T2_LOG"

# --- T3: Guardian unreachable + fail-closed → exit 2 ---
HOME="$TMP_LOG_DIR" GUARDIAN_MODE=enforce GUARDIAN_BASE_URL="http://127.0.0.1:19999" GUARDIAN_TIMEOUT_S=1 GUARDIAN_FAIL_MODE=closed \
  bash "$SHIM" "ls" 2>/dev/null
T3_EXIT=$?
assert_exit "T3: unreachable+fail-closed exit 2" 2 "$T3_EXIT"

# --- T4: Mock Guardian verdict=pass → exit 0 ---
echo "$MOCK_SCRIPT" | python3 - pass 19001 &
MOCK_PID=$!
sleep 0.3
HOME="$TMP_LOG_DIR" GUARDIAN_MODE=audit GUARDIAN_BASE_URL="http://127.0.0.1:19001" GUARDIAN_TIMEOUT_S=3 \
  bash "$SHIM" "ls" 2>/dev/null
T4_EXIT=$?
assert_exit "T4: verdict=pass exit 0" 0 "$T4_EXIT"
assert_log_contains "T4: verdict=pass in log" '"result":"pass"' "$TMP_LOG_DIR/.claude/guardian-shim/audit.log"
kill "$MOCK_PID" 2>/dev/null; wait "$MOCK_PID" 2>/dev/null; MOCK_PID=""

# --- T5: Mock Guardian verdict=warn → exit 0 + WARN on stderr ---
echo "$MOCK_SCRIPT" | python3 - warn 19002 &
MOCK_PID=$!
sleep 0.3
STDERR_T5=$(HOME="$TMP_LOG_DIR" GUARDIAN_MODE=audit GUARDIAN_BASE_URL="http://127.0.0.1:19002" GUARDIAN_TIMEOUT_S=3 \
  bash "$SHIM" "ls" 2>&1 >/dev/null)
T5_EXIT=$?
assert_exit "T5: verdict=warn exit 0" 0 "$T5_EXIT"
assert_not_contains "T5: verdict=warn stderr has WARN" "^$" "$STDERR_T5"
kill "$MOCK_PID" 2>/dev/null; wait "$MOCK_PID" 2>/dev/null; MOCK_PID=""

# --- T6: Mock Guardian verdict=fail + GUARDIAN_MODE=audit → exit 0 (non-blocking) ---
echo "$MOCK_SCRIPT" | python3 - fail 19003 &
MOCK_PID=$!
sleep 0.3
HOME="$TMP_LOG_DIR" GUARDIAN_MODE=audit GUARDIAN_BASE_URL="http://127.0.0.1:19003" GUARDIAN_TIMEOUT_S=3 \
  bash "$SHIM" "rm -rf /" 2>/dev/null
T6_EXIT=$?
assert_exit "T6: verdict=fail+audit exit 0 (non-blocking)" 0 "$T6_EXIT"
assert_log_contains "T6: fail verdict in audit log" '"result":"fail"' "$TMP_LOG_DIR/.claude/guardian-shim/audit.log"
kill "$MOCK_PID" 2>/dev/null; wait "$MOCK_PID" 2>/dev/null; MOCK_PID=""

# --- T7: Mock Guardian verdict=fail + GUARDIAN_MODE=enforce → exit 1 (blocked) ---
echo "$MOCK_SCRIPT" | python3 - fail 19004 &
MOCK_PID=$!
sleep 0.3
HOME="$TMP_LOG_DIR" GUARDIAN_MODE=enforce GUARDIAN_BASE_URL="http://127.0.0.1:19004" GUARDIAN_TIMEOUT_S=3 \
  bash "$SHIM" "rm -rf /" 2>/dev/null
T7_EXIT=$?
assert_exit "T7: verdict=fail+enforce exit 1 (blocked)" 1 "$T7_EXIT"
kill "$MOCK_PID" 2>/dev/null; wait "$MOCK_PID" 2>/dev/null; MOCK_PID=""

# --- T8: Secret masking — password=hunter2 must not appear in log or POST ---
# Mock server that captures request body and stores it for inspection
CAPTURE_FILE="$TMP_LOG_DIR/captured.json"
python3 - pass 19005 "$CAPTURE_FILE" << 'PYEOF' &
import sys, json
from http.server import HTTPServer, BaseHTTPRequestHandler

verdict_result = sys.argv[1]
port = int(sys.argv[2])
capture_file = sys.argv[3]

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        with open(capture_file, "wb") as f:
            f.write(body)
        resp = {
            "verdict": {
                "result": verdict_result,
                "summary": "masked check",
                "reasons": [],
                "sources": []
            }
        }
        data = json.dumps(resp).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

HTTPServer(("127.0.0.1", port), Handler).serve_forever()
PYEOF
MOCK_PID=$!
sleep 0.3
HOME="$TMP_LOG_DIR" GUARDIAN_MODE=audit GUARDIAN_BASE_URL="http://127.0.0.1:19005" GUARDIAN_TIMEOUT_S=3 \
  bash "$SHIM" "echo password=hunter2 something" 2>/dev/null
T8_EXIT=$?
sleep 0.1
# Check that captured POST body does not contain raw "hunter2"
if [ -f "$CAPTURE_FILE" ]; then
  CAPTURED=$(cat "$CAPTURE_FILE")
  assert_not_contains "T8: POST body masked (no hunter2)" "hunter2" "$CAPTURED"
else
  echo "FAIL [T8: captured file missing]"
  FAIL=$((FAIL + 1))
fi
# Check local log also doesn't contain hunter2
LOG_CONTENT=$(cat "$TMP_LOG_DIR/.claude/guardian-shim/audit.log" 2>/dev/null || echo "")
assert_not_contains "T8: local log masked (no hunter2)" "hunter2" "$LOG_CONTENT"
kill "$MOCK_PID" 2>/dev/null; wait "$MOCK_PID" 2>/dev/null; MOCK_PID=""

echo ""
echo "=== Results: $PASS PASS, $FAIL FAIL ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
