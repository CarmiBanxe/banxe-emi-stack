#!/usr/bin/env bash
# pre-push — ADR-060 branch-name + ADR-158 push-safety (G-5+) + ADR-160 write-gate (G-1..G-4) guards (v2)
#
# Guard stack (all must pass):
#   G-1 Force-refspec guard  (ADR-160 D-2): block any refspec with '+' prefix
#   G-2 Worktree guard       (ADR-160 D-2): block push from main checkout (ADR-120)
#   G-3 Stash guard          (ADR-160 D-2): block push when stash is non-empty
#   G-4 Role-guard           (ADR-160 D-2): block push if .TERMINAL-ROLE absent (FAIL not WARN)
#   G-5 Branch-name guard    (ADR-060):     block non-compliant branch namespace
#   G-5+ Protected-ref guard (ADR-158):     block direct push to main/master (remote ref)
#
# Override env vars (operator-only, set in shell before push):
#   ALLOW_FORCE_WITH_LEASE=1  — allow --force-with-lease (not bare +refspec)
#   ALLOW_MAIN_CHECKOUT=1     — skip worktree check
#   ALLOW_STASH=1             — skip stash check
#
# Install (banxe-architecture):  git config core.hooksPath .githooks
# Install (banxe-emi-stack):     cp .githooks/pre-push ~/banxe-emi-stack/.githooks/pre-push
#                                git -C ~/banxe-emi-stack config core.hooksPath .githooks
#
# Source: ADR-060 (branch naming), ADR-158 (push-safety G-5+), ADR-160 (write-gate G-1..G-4), ADR-120 (worktree mandate)
set -eu

# ── ADR-060 — Branch naming pattern (G-5) ─────────────────────────────────────
# specproj = ADR-TERMINAL-B-SPEC-LANE Terminal-B namespace
PATTERN='^agent/(central|right|factory|specproj)/[A-Za-z0-9]+/[a-z0-9._-]+$'

is_compliant() {
  b="${1#refs/heads/}"
  case "$b" in
    main|master|HEAD|dependabot/*|renovate/*|revert/*) return 0 ;;
  esac
  printf '%s\n' "$b" | grep -qE "$PATTERN"
}

_branch_violation() {
  echo "✗ pre-push BLOCKED — G-5 branch '$1' violates ADR-060 namespace." >&2
  echo "  Required: agent/(central|right|factory|specproj)/<id>/<slug>" >&2
  echo "  <id> = [A-Za-z0-9]+  (hyphen FORBIDDEN)" >&2
  echo "  <slug> = [a-z0-9._-]+ (lowercase; hyphens allowed)" >&2
}

# ── ADR-158 G-5+ — Protected-ref guard ────────────────────────────────────────
# Blocks direct push whose REMOTE ref is a protected integration branch.
# Ported from pre-push v1 (origin/main 2026-07-04 addition).
is_protected_ref() {
  r="${1#refs/heads/}"
  case "$r" in
    main|master) return 0 ;;
    *) return 1 ;;
  esac
}

_push_violation() {
  echo "✗ pre-push BLOCKED (ADR-158) — direct push to protected ref '$1' is forbidden." >&2
  echo "  Integrate via PR merge (ADR-060/ADR-102). Never push main/master directly." >&2
}

# ── ADR-160 G-1 — Force-refspec guard ─────────────────────────────────────────
_check_force_refspec() {
  local rc=0
  if [ -n "${GIT_PUSH_REFSPEC:-}" ]; then
    case "$GIT_PUSH_REFSPEC" in
      +*) echo "✗ pre-push BLOCKED — G-1 force-refspec '+' detected. Use --force-with-lease, not bare +." >&2; rc=1 ;;
    esac
  fi
  return "$rc"
}

# ── ADR-160 G-2 — Worktree guard ──────────────────────────────────────────────
_check_worktree() {
  if [ "${ALLOW_MAIN_CHECKOUT:-0}" = "1" ]; then return 0; fi
  # Portable detection: a linked worktree's git-dir lives under .git/worktrees/
  case "$(git rev-parse --absolute-git-dir 2>/dev/null || echo /)" in
    */worktrees/*) return 0 ;;
    *)
      echo "✗ pre-push BLOCKED — G-2 pushing from main checkout violates ADR-120." >&2
      echo "  Use a worktree: git worktree add ~/wt/<name> -b <branch>" >&2
      echo "  Or set ALLOW_MAIN_CHECKOUT=1 to override (operator only)." >&2
      return 1 ;;
  esac
}

# ── ADR-160 G-3 — Stash guard ─────────────────────────────────────────────────
_check_stash() {
  if [ "${ALLOW_STASH:-0}" = "1" ]; then return 0; fi
  local stash_count
  stash_count="$(git stash list 2>/dev/null | wc -l | tr -d ' ')"
  if [ "${stash_count:-0}" -gt 0 ]; then
    echo "✗ pre-push BLOCKED — G-3 ${stash_count} stash entries found." >&2
    echo "  Pop or drop stash before pushing, or set ALLOW_STASH=1 to override." >&2
    echo "  Stash list:" >&2
    git stash list >&2
    return 1
  fi
  return 0
}

# ── ADR-160 G-4 — Role-guard (hard FAIL) ──────────────────────────────────────
_check_role() {
  local root
  root="$(git rev-parse --show-toplevel 2>/dev/null || echo '')"
  if [ -z "$root" ] || [ ! -f "${root}/.TERMINAL-ROLE" ]; then
    echo "✗ pre-push BLOCKED — G-4 .TERMINAL-ROLE anchor not found in repo root." >&2
    echo "  Every terminal must have a .TERMINAL-ROLE file before pushing." >&2
    echo "  Create it: echo 'FACTORY' > .TERMINAL-ROLE  (or CENTRAL, TERMINAL-A, TERMINAL-B)" >&2
    return 1
  fi
  local role
  role="$(cat "${root}/.TERMINAL-ROLE" | head -1 | tr -d '[:space:]')"
  echo "pre-push G-4 role: ${role} ✓"
  return 0
}

# ── Main ───────────────────────────────────────────────────────────────────────
_main() {
  local rc=0

  # G-1: Force-refspec (env-based)
  _check_force_refspec || rc=1

  # G-2: Worktree guard
  _check_worktree || rc=1

  # G-3: Stash guard
  _check_stash || rc=1

  # G-4: Role guard (hard fail)
  _check_role || rc=1

  # Early exit if any ADR-160 write-gate (or ADR-158 push-safety) guard failed
  [ "$rc" -eq 0 ] || return "$rc"

  # G-5: ADR-060 branch-name guard + G-5+ protected-ref guard (STDIN refs)
  local checked=0
  while read -r local_ref _lsha _rref _rsha; do
    [ -n "${local_ref:-}" ] || continue
    case "$local_ref" in
      refs/heads/*) : ;;
      *) continue ;;
    esac
    checked=1
    b="${local_ref#refs/heads/}"
    if is_compliant "$b"; then
      echo "pre-push G-5 OK (ADR-060: $b)"
    else
      _branch_violation "$b"
      rc=1
    fi
    # G-5+: block direct push to protected remote ref (main/master)
    if is_protected_ref "${_rref:-}"; then
      _push_violation "${_rref#refs/heads/}"
      rc=1
    fi
  done

  # Manual / empty-STDIN invocation — fall back to current branch
  if [ "$checked" -eq 0 ]; then
    b="$(git symbolic-ref --short -q HEAD || echo '')"
    [ -n "$b" ] || { echo "pre-push: detached HEAD, nothing to validate"; return 0; }
    if is_compliant "$b"; then
      echo "pre-push G-5 OK (ADR-060: $b)"
    else
      _branch_violation "$b"
      rc=1
    fi
  fi

  return "$rc"
}

# Execute only when run directly (not when sourced by test harness)
if [ "${BASH_SOURCE[0]:-$0}" = "$0" ]; then
  _main
fi
