#!/usr/bin/env bash
# verify_grok_setup.sh — read-only verification of the Grok CLI + fable-advisor setup.
# Makes no changes. Safe to run before or after installation.
set -uo pipefail

pass=0
fail=0

check() {
  local desc="$1" ok="$2"
  if [ "$ok" = "0" ]; then
    echo "[OK]   $desc"
    pass=$((pass + 1))
  else
    echo "[MISS] $desc"
    fail=$((fail + 1))
  fi
}

echo "=== verify_grok_setup.sh ($(date -u +%FT%TZ)) ==="
echo

command -v grok >/dev/null 2>&1
check "grok CLI on PATH" $?

if command -v grok >/dev/null 2>&1; then
  echo "  version: $(grok --version 2>&1 | head -1)"
  grok models >/dev/null 2>&1
  check "grok authenticated (grok models succeeds)" $?
else
  echo "  (skipped: grok models — grok not on PATH)"
  fail=$((fail + 1))
fi

[ -x "$HOME/.grok/bin/grok" ]
check "\$HOME/.grok/bin/grok binary present" $?

[ -f "$HOME/.grok/auth.json" ] || env | grep -qE '^(GROK_DEPLOYMENT_KEY|XAI_API_KEY)'
check "grok auth source present (auth.json or deployment key env)" $?

[ -d "external/fable-advisor/.claude-plugin" ]
check "external/fable-advisor plugin manifest present (local repo)" $?

[ -f "external/fable-advisor/agents/grok-implementer.md" ]
check "grok-implementer agent file present" $?

echo
echo "=== SUMMARY: $pass OK / $fail missing ==="
if [ "$fail" -gt 0 ]; then
  echo "Not fully wired yet. See docs/setup/FABLE-GROK-SETUP.md for the remaining steps."
  exit 1
fi
echo "Grok CLI + fable-advisor local prerequisites verified."
