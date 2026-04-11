#!/usr/bin/env bash
# validate-context.sh — Validate Claude Code governance context is in place
# IL-SK-01 | Created: 2026-04-11

set -euo pipefail

ERRORS=0

check() {
    local description="$1"
    local path="$2"
    if [ -e "$path" ]; then
        echo "  OK  $description ($path)"
    else
        echo "MISSING $description ($path)"
        ERRORS=$((ERRORS + 1))
    fi
}

echo "=== BANXE AI Bank — Context Validation ==="
echo ""

echo "--- Core governance ---"
check "Root CLAUDE.md"                      "CLAUDE.md"
check ".claude/CLAUDE.md"                   ".claude/CLAUDE.md"

echo ""
echo "--- Rules ---"
check "Global rules (00-global)"            ".claude/rules/00-global.md"
check "Financial invariants"                ".claude/rules/financial-invariants.md"
check "Security policy"                     ".claude/rules/security-policy.md"
check "Agent authority"                     ".claude/rules/agent-authority.md"

echo ""
echo "--- Commands ---"
check "plan-feature command"                ".claude/commands/plan-feature.md"
check "review-pr command"                   ".claude/commands/review-pr.md"
check "incident-analysis command"           ".claude/commands/incident-analysis.md"

echo ""
echo "--- Specs ---"
check "Feature spec template"               ".claude/specs/feature-spec-template.md"
check "Incident template"                   ".claude/specs/incident-template.md"

echo ""
echo "--- GitHub ---"
check "PR template"                         ".github/PULL_REQUEST_TEMPLATE.md"
check "Quality gate workflow"               ".github/workflows/quality-gate.yml"

echo ""
echo "--- Semgrep ---"
check "Banxe SAST rules"                    ".semgrep/banxe-rules.yml"

echo ""
echo "--- AI registries ---"
check "AI soul"                             ".ai/soul.md"

echo ""

if [ "$ERRORS" -gt 0 ]; then
    echo "VALIDATION FAILED: $ERRORS missing item(s). Run scripts/bootstrap.sh to create directories."
    exit 1
else
    echo "VALIDATION PASSED: all required context files present."
    exit 0
fi
