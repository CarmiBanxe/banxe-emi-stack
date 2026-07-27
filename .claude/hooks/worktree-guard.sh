#!/usr/bin/env bash
# worktree-guard.sh — ISO-FIX-01 advisory guard, NOT wired into settings.json.
#
# Refuses a proposed worktree target when it is (a) nested inside a repo tree,
# or (b) an EXISTING worktree that is currently dirty. Prints a clear reason
# and exits non-zero. Exits 0 (silent) when the target looks safe.
#
# This script does not delete, move, or modify anything — it only inspects
# and reports. Registration is manual and requires operator sign-off; see the
# "Registering this guard" section below.
#
# Usage:
#   .claude/hooks/worktree-guard.sh <target-path> [branch-name]
#
# Exit codes:
#   0  target looks safe (outside any repo tree, and if it already exists,
#      currently clean)
#   1  target path is nested inside a git repo tree (isolation violation)
#   2  target path already exists as a worktree and is dirty
#   3  usage error

set -euo pipefail

target="${1:-}"
branch="${2:-}"

if [[ -z "$target" ]]; then
  echo "usage: $(basename "$0") <target-path> [branch-name]" >&2
  exit 3
fi

# Resolve to an absolute path without requiring the path to exist yet.
resolved="$(python3 -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$target" 2>/dev/null || readlink -m -- "$target")"

# Rule 1: refuse targets nested inside ANY git repo tree (not just this one).
# Walk up from the target looking for a .git entry that is not the target's
# own future worktree metadata (a worktree add creates .git as a *file*
# inside the new dir, so we only check strictly-parent directories).
dir="$(dirname -- "$resolved")"
while [[ "$dir" != "/" ]]; do
  if [[ -e "$dir/.git" ]]; then
    cat >&2 <<EOF
REFUSED: worktree target is nested inside an existing repo tree.

  target:      $resolved
  repo found:  $dir  (contains .git)

Per .claude/WORKTREE-ISOLATION-POLICY.md rule 2, worktrees must be created
OUTSIDE the repo tree (e.g. /home/mmber/wt/<id>), never as a subdirectory of
a repo. A nested worktree pollutes 'git status'/'grep -r'/'find' run from the
parent repo's root.
EOF
    exit 1
  fi
  dir="$(dirname -- "$dir")"
done

# Rule 2: if the target already exists and is itself a worktree, refuse if dirty.
if [[ -d "$resolved/.git" || -f "$resolved/.git" ]]; then
  if git -C "$resolved" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    dirty_count="$(git -C "$resolved" status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
    if [[ "$dirty_count" != "0" ]]; then
      cat >&2 <<EOF
REFUSED: target worktree already exists and is DIRTY ($dirty_count entries).

  target: $resolved

Per .claude/WORKTREE-ISOLATION-POLICY.md rule 3, a task's working tree must
be clean before the task starts. Commit, stash ('git stash push -m "..."'),
or otherwise resolve the existing changes before reusing this worktree.
EOF
      exit 2
    fi
  fi
fi

if [[ -n "$branch" ]]; then
  if ! [[ "$branch" =~ ^agent/(central|right|factory|specproj)/[A-Za-z0-9]+/[a-z0-9._-]+$ ]]; then
    cat >&2 <<EOF
WARNING: branch name does not match ADR-060 (^agent/(central|right|factory|specproj)/[A-Za-z0-9]+/[a-z0-9._-]+\$):
  $branch
(non-blocking — advisory only)
EOF
  fi
fi

exit 0
