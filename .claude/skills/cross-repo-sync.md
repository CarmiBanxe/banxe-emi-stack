---
name: cross-repo-sync
description: Check sync status across all 13 BANXE repositories
context: fork
agent: Explore
allowed-tools: Bash(git *), Bash(ls *), Bash(cat *)
---

## Cross-Repo Sync Status

- banxe-emi-stack: `!cd /home/mmber/banxe-emi-stack && git log --oneline -1 && git status --short | wc -l | xargs echo "dirty:"`
- banxe-platform: `!cd /home/mmber/banxe-platform && git log --oneline -1 && git status --short | wc -l | xargs echo "dirty:" 2>/dev/null || echo "not found"`
- banxe-ui: `!cd /home/mmber/banxe-ui && git log --oneline -1 && git status --short | wc -l | xargs echo "dirty:" 2>/dev/null || echo "not found"`
- banxe-architecture: `!cd /home/mmber/banxe-architecture && git log --oneline -1 && git status --short | wc -l | xargs echo "dirty:" 2>/dev/null || echo "not found"`
- banxe-infra: `!cd /home/mmber/banxe-infra && git log --oneline -1 && git status --short | wc -l | xargs echo "dirty:" 2>/dev/null || echo "not found"`
- banxe-training-data: `!cd /home/mmber/banxe-training-data && git log --oneline -1 && git status --short | wc -l | xargs echo "dirty:" 2>/dev/null || echo "not found"`
- banxe-lexisnexis-distro: `!cd /home/mmber/banxe-lexisnexis-distro && git log --oneline -1 && git status --short | wc -l | xargs echo "dirty:" 2>/dev/null || echo "not found"`
- MetaClaw: `!cd /home/mmber/MetaClaw && git log --oneline -1 && git status --short | wc -l | xargs echo "dirty:" 2>/dev/null || echo "not found"`
- MiroFish: `!cd /home/mmber/MiroFish && git log --oneline -1 && git status --short | wc -l | xargs echo "dirty:" 2>/dev/null || echo "not found"`
- developer-core: `!cd /home/mmber/developer-core && git log --oneline -1 && git status --short | wc -l | xargs echo "dirty:" 2>/dev/null || echo "not found"`
- vibe-coding: `!cd /home/mmber/vibe-coding && git log --oneline -1 && git status --short | wc -l | xargs echo "dirty:" 2>/dev/null || echo "not found"`
- obsidian-vault: `!cd /home/mmber/obsidian-vault && git log --oneline -1 && git status --short | wc -l | xargs echo "dirty:" 2>/dev/null || echo "not found"`
- banxe-mirofish: `!cd /home/mmber/banxe-mirofish && git log --oneline -1 && git status --short | wc -l | xargs echo "dirty:" 2>/dev/null || echo "not found"`

## Your task

Review the cross-repo state above:

1. Identify repos with dirty working trees (uncommitted changes)
2. Flag repos that appear behind remote (no recent commits vs others)
3. Check if any shared files (CLAUDE.md templates, pre-commit configs, AGENTS.md) diverged between repos
4. List repos where `.claude/CLAUDE.md` may be out of date vs the canonical version in `banxe-architecture`
5. Suggest a sync plan: which repos need `git pull`, which need new commits pushed

Output a per-repo table: **IN SYNC / DIRTY / STALE / MISSING**.

> Note: collaboration repo was archived and removed from this list (previously 14 repos).
