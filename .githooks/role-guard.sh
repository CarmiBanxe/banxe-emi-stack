#!/usr/bin/env bash
# role-guard.sh — enforces docs/canon/operating-mode.md (Central <-> Factory).
# CANON (operating-mode.md §3): "Mutations only via Factory or the operator."
#   - Factory (Claude Code) MUTATES: writes/commits product code (services/*.py etc.) — this IS its job
#     (full-cycle IT company: build, save, analyse, document).
#   - Central (SHELL) is READ-ONLY diagnostics; it NEVER mutates project repos directly.
# So the guard does NOT forbid Factory from committing code (the old orphaned guard did — it
# contradicted this canon and is retired). The guard only enforces the read-only Central boundary
# and requires a role anchor.
set -euo pipefail
root="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
anchor="$root/.TERMINAL-ROLE"
[ -f "$anchor" ] || { echo "[role-guard] WARN: no .TERMINAL-ROLE — skipping"; exit 0; }
role="$(tr '[:lower:]' '[:upper:]' < "$anchor" | grep -oE 'FACTORY|CENTRAL' | head -1)"
staged="$(git diff --cached --name-only)"
[ -z "$staged" ] && exit 0

case "$role" in
  CENTRAL)
    # Canon §1/§3: Central is read-only, must not mutate project repos. Any staged change is a violation.
    echo "[role-guard] BLOCKED (CENTRAL): Central is read-only per operating-mode.md §3."
    echo "[role-guard] Mutations must go through Factory (Claude Code) or the operator."
    exit 1
    ;;
  FACTORY|"")
    # Canon §2/§3: Factory mutates code — this is allowed and expected. No path restriction on product code.
    echo "[role-guard] OK (FACTORY): full-cycle mutations permitted per operating-mode.md."
    ;;
esac
