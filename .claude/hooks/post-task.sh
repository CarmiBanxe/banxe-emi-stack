#!/usr/bin/env bash
# .claude/hooks/post-task.sh — Post-task documentation health check
# IL-091 | 2026-04-12
#
# After Claude finishes a task:
#   1. git status  — uncommitted changes?
#   2. last commit — within 5 minutes?
#   3. If yes     — run scripts/doc-sync.py (Mechanism 3)
#   4. Summary    — updated docs | requires manual attention
#
# Register in .claude/settings.json as a Stop hook for automatic execution:
#   "Stop": [{"hooks": [{"type": "command",
#     "command": "bash /home/mmber/banxe-emi-stack/.claude/hooks/post-task.sh"}]}]
#
# SAFE: all logic inside _main(); always exits 0.

# ── Constants ──────────────────────────────────────────────────────────────────

readonly SYNC_THRESHOLD=300   # seconds — commits older than this skip doc-sync
readonly BAR="════════════════════════════════════════════════════════════"
readonly DIV="────────────────────────────────────────────────────────────"

# ── Age formatter ──────────────────────────────────────────────────────────────

_age() {
    local secs="$1"
    if   [ "${secs}" -lt  60 ];  then printf '%ds'  "${secs}"
    elif [ "${secs}" -lt 3600 ]; then printf '%dm'  "$(( secs / 60 ))"
    else                              printf '%dh'  "$(( secs / 3600 ))"
    fi
}

# ── Line counter (handles empty input without returning 1) ─────────────────────

_count_lines() {
    local text="$1"
    [ -z "${text}" ] && echo 0 && return
    printf '%s\n' "${text}" | grep -c '.' || echo 0
}

# ── Main ───────────────────────────────────────────────────────────────────────

_main() {

    # Resolve repo root from this file's location (.claude/hooks/ → ../../)
    local repo_dir
    repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
    cd "${repo_dir}"

    # ── Gather state ───────────────────────────────────────────────────────────

    local short_hash subject commit_ts now_ts age_secs dirty

    short_hash="$(git log -1 --format=%h    2>/dev/null || echo '?')"
    subject="$(   git log -1 --format=%s    2>/dev/null || echo '(no commits yet)')"
    commit_ts="$( git log -1 --format=%ct   2>/dev/null || echo 0)"
    now_ts="$(date +%s)"
    age_secs=$(( now_ts - commit_ts ))
    dirty="$(git status --porcelain 2>/dev/null || true)"

    # ── Header ─────────────────────────────────────────────────────────────────

    printf '\n%s\n' "${BAR}"
    printf '  post-task  %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf '%s\n' "${BAR}"

    # ── 1. git status ──────────────────────────────────────────────────────────

    if [ -n "${dirty}" ]; then
        local n_dirty
        n_dirty="$(_count_lines "${dirty}")"
        printf '  git status    ⚠️  %d uncommitted change(s)\n' "${n_dirty}"
        # Show up to 5 changed paths, indented
        printf '%s\n' "${dirty}" | head -5 | sed 's/^/    /'
        [ "${n_dirty}" -gt 5 ] && printf '    … (%d more files)\n' "$(( n_dirty - 5 ))"
    else
        printf '  git status    ✅ clean\n'
    fi

    # ── 2. Last commit ─────────────────────────────────────────────────────────

    printf '  last commit   %s  %s ago  %s\n' \
        "${short_hash}" "$(_age "${age_secs}")" "${subject}"

    # ── 3. doc-sync ────────────────────────────────────────────────────────────

    printf '\n  %s\n' "${DIV}"

    if [ "${age_secs}" -ge "${SYNC_THRESHOLD}" ]; then
        # No recent commit — skip doc-sync, show hint
        printf '  ℹ️  Last commit %s ago — doc-sync skipped (threshold: %ds)\n' \
            "$(_age "${age_secs}")" "${SYNC_THRESHOLD}"
        printf '     Run manually:  python3 scripts/doc-sync.py --commit %s\n' "${short_hash}"
        printf '%s\n\n' "${BAR}"
        return
    fi

    if [ ! -f "${repo_dir}/scripts/doc-sync.py" ]; then
        printf '  ❌ scripts/doc-sync.py not found — doc-sync skipped\n'
        printf '%s\n\n' "${BAR}"
        return
    fi

    printf '  doc-sync → commit %s (%s ago)\n' "${short_hash}" "$(_age "${age_secs}")"
    printf '  %s\n' "${DIV}"

    # Run doc-sync, suppress its own decorative separators from this output
    local sync_raw
    sync_raw="$(python3 "${repo_dir}/scripts/doc-sync.py" --commit "${short_hash}" 2>&1)"

    # ── 4. Partition output: updated vs attention ───────────────────────────────

    # ✅ lines  → auto-updated
    local updated_lines
    updated_lines="$(printf '%s\n' "${sync_raw}" | grep -F '✅' | sed 's/^[[:space:]]*/  /' || true)"

    # ⚠️ ❌ ⏭️  lines → require manual attention or were skipped
    local attention_lines
    attention_lines="$(printf '%s\n' "${sync_raw}" \
        | grep -vF '✅' \
        | grep -vF '─' \
        | grep -vE '^\[|^Would|^[[:space:]]*$|Document|doc-sync' \
        | grep -E '.' \
        | sed 's/^[[:space:]]*/  /' \
        || true)"

    # Print updated section
    if [ -n "${updated_lines}" ]; then
        printf '  Updated:\n'
        printf '%s\n' "${updated_lines}"
    fi

    # Print attention section
    if [ -n "${attention_lines}" ]; then
        printf '\n  Needs attention:\n'
        printf '%s\n' "${attention_lines}"
    fi

    # ── Summary counts ─────────────────────────────────────────────────────────

    local n_updated n_attention
    n_updated="$(  _count_lines "${updated_lines}")"
    n_attention="$(_count_lines "${attention_lines}")"

    printf '\n  %s\n' "${DIV}"
    printf '  ✅ updated:  %d doc(s)' "${n_updated}"

    if [ "${n_attention}" -gt 0 ]; then
        printf '   ⚠️  manual: %d doc(s)\n' "${n_attention}"
    else
        printf '\n'
    fi

    printf '%s\n\n' "${BAR}"

}  # end _main

_main || true
exit 0
