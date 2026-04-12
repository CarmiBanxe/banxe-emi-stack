---
name: pr-review
description: Full code review of current PR with BANXE compliance and quality standards
context: fork
agent: Analyze
allowed-tools: Bash(gh *), Bash(git *), Bash(ruff *), Bash(semgrep *)
---

## PR Context

- PR diff: `!gh pr diff 2>/dev/null || echo "No active PR"`
- Changed files: `!gh pr diff --name-only 2>/dev/null || echo "No active PR"`
- PR description & comments: `!gh pr view --comments 2>/dev/null || echo "No active PR"`
- CI status: `!gh pr checks 2>/dev/null || echo "No active PR"`
- Ruff on changed files: `!gh pr diff --name-only 2>/dev/null | grep "\.py$" | xargs ruff check 2>&1 | tail -10 || echo "No Python files changed"`
- Semgrep on changed files: `!gh pr diff --name-only 2>/dev/null | xargs semgrep --config .semgrep/ 2>&1 | tail -10 || echo "No semgrep config"`
- Recent commits: `!git log --oneline -10`

## Your task

Perform a thorough code review with focus on BANXE-specific concerns:

**Security & Compliance**
- Check for hardcoded secrets, credentials, or API keys
- Verify AML/KYC rule changes are documented and tested
- Flag any changes to transaction limits or risk thresholds
- Check against FCA CASS 15 requirements

**Code Quality**
- Identify logic errors, edge cases, or missing validations
- Check error handling for external API calls (LexisNexis, Watchman, payment rails)
- Verify database migrations are reversible
- Ruff clean (0 errors), Semgrep clean (0 findings)

**Architecture**
- Check alignment with FastAPI/microservices patterns
- Verify new endpoints have proper authentication/authorization
- Flag any direct DB access that bypasses the service layer
- Check consistency with banxe-architecture invariants

Output: structured review with **BLOCKER / MAJOR / MINOR / SUGGESTION** labels per finding.
