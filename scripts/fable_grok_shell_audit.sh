#!/usr/bin/env bash
# fable_grok_shell_audit.sh — read-only audit for the fable-advisor/Grok setup.
# No mutations. Safe to re-run at any time.
set -euo pipefail

echo "=== FABLE/GROK SHELL AUDIT ($(date -u +%FT%TZ)) ==="

echo
echo "--- grok CLI ---"
if command -v grok >/dev/null 2>&1; then
  echo "grok: FOUND at $(command -v grok)"
  grok --version 2>&1 || echo "grok --version failed"
else
  echo "grok: NOT FOUND on PATH"
fi

echo
echo "--- GROK_*/XAI_API_KEY env vars ---"
if env | grep -qE '^(GROK_|XAI_API_KEY)'; then
  env | grep -E '^(GROK_|XAI_API_KEY)' | sed -E 's/=.*/=<redacted>/'
else
  echo "none set"
fi

echo
echo "--- external/fable-advisor ---"
if [ -d "external/fable-advisor" ]; then
  echo "present: external/fable-advisor"
  [ -f "external/fable-advisor/.claude-plugin/marketplace.json" ] && echo "  has .claude-plugin/marketplace.json"
  [ -f "external/fable-advisor/.claude-plugin/plugin.json" ] && echo "  has .claude-plugin/plugin.json"
  [ -f "external/fable-advisor/README.md" ] && echo "  has README.md"
else
  echo "MISSING: external/fable-advisor"
fi

echo
echo "--- external/loop-engineering ---"
if [ -d "external/loop-engineering/.git" ]; then
  echo "present: external/loop-engineering (git repo)"
else
  echo "MISSING: external/loop-engineering/.git"
fi

echo
echo "--- .claude/ and plugin manifests ---"
[ -d ".claude" ] && echo ".claude/: present" || echo ".claude/: MISSING"
[ -d ".claude-plugin" ] && echo ".claude-plugin/ (repo root): present" || echo ".claude-plugin/ (repo root): MISSING"
find . -maxdepth 4 -iname "marketplace.json" 2>/dev/null | sed 's/^/  marketplace.json: /'
find . -maxdepth 4 -iname "SKILL.md" 2>/dev/null | sed 's/^/  SKILL.md: /'

echo
echo "=== STATUS SUMMARY ==="
command -v grok >/dev/null 2>&1 && echo "grok CLI: INSTALLED" || echo "grok CLI: NOT INSTALLED"
env | grep -qE '^(GROK_|XAI_API_KEY)' && echo "grok auth env: SET" || echo "grok auth env: NOT SET"
[ -d "external/fable-advisor/.claude-plugin" ] && echo "fable-advisor plugin manifest: FOUND" || echo "fable-advisor plugin manifest: NOT FOUND"
[ -d "external/loop-engineering/.git" ] && echo "loop-engineering: PRESENT" || echo "loop-engineering: MISSING"
