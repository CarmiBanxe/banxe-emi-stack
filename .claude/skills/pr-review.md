---
name: pr-review
description: Full code review of current PR with BANXE compliance and quality standards
user-invocable: false
disable-model-invocation: true
context: fork
agent: Analyze
allowed-tools: Bash(gh *), Bash(git *), Bash(ruff *), Bash(semgrep *)
---

## PR Context

- PR diff: `!gh pr diff 2>/dev/null || echo "No active PR"`
- Changed files: `!gh pr diff --name-only 2>/dev/null || echo "No active PR"`

## Review Checklist

1. Financial invariants (I-01..I-27)
2. Ruff clean
3. Semgrep clean
4. Tests added
5. INSTRUCTION-LEDGER updated
