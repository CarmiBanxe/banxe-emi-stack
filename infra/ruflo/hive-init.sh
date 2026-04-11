#!/usr/bin/env bash
# Ruflo Hive Mind — BANXE UI Sprint Initialization
# IL-ADDS-01 | 8-agent hierarchical topology
# Usage: bash infra/ruflo/hive-init.sh

set -euo pipefail

CONTEXT_FILE="$(dirname "$0")/queen-agent-context.md"

echo "🐝 Initializing BANXE Hive Mind..."
echo "   Topology: hierarchical | Agents: 8 | Memory: 512MB"

# ─── 1. Initialize hive ────────────────────────────────────────────────────────
npx claude-flow hive init \
  --topology hierarchical \
  --agents 8 \
  --memory-size 512MB \
  --context-file "$CONTEXT_FILE"

echo "✅ Hive initialized"

# ─── 2. Spawn specialized agents ──────────────────────────────────────────────
echo "🤖 Spawning agents..."

npx claude-flow coordination agent-spawn \
  --type researcher \
  --name Design-Researcher \
  --description "Reads DESIGN.md tokens, researches WCAG AA requirements, prepares component specs"

npx claude-flow coordination agent-spawn \
  --type architect \
  --name UI-Architect \
  --description "Designs component interfaces, plans module structure, reviews CVA variants"

npx claude-flow coordination agent-spawn \
  --type coder \
  --name Dashboard-Dev \
  --description "Implements DashboardPage.tsx — KPI cards, transactions table, AML feed"

npx claude-flow coordination agent-spawn \
  --type coder \
  --name AML-Dev \
  --description "Implements AMLMonitor.tsx — alert table, risk heatmap, case detail panel"

npx claude-flow coordination agent-spawn \
  --type coder \
  --name KYC-Dev \
  --description "Implements KYCWizard.tsx — 5-step wizard, file upload, consent flows"

npx claude-flow coordination agent-spawn \
  --type tester \
  --name UI-Tester \
  --description "Writes Vitest + Playwright tests, validates WCAG AA, verifies tabular-nums"

npx claude-flow coordination agent-spawn \
  --type reviewer \
  --name Design-QA \
  --description "Runs visual diff against DESIGN.md, checks for hardcoded hex, audits consent flows"

echo "✅ All 7 specialist agents spawned (+ Queen)"

# ─── 3. Orchestrate sprint task ────────────────────────────────────────────────
echo "🎯 Orchestrating sprint..."

npx claude-flow coordination task-orchestrate \
  --task "Complete BANXE UI Sprint" \
  --strategy parallel \
  --phases "
    Phase 1: Design-Researcher reads DESIGN.md + ARCHITECTURE-AI-DESIGN-SYSTEM.md
    Phase 2: UI-Architect plans component interfaces + module layout
    Phase 3 (parallel): Dashboard-Dev + AML-Dev + KYC-Dev implement modules
    Phase 4: UI-Tester writes tests for all components
    Phase 5: Design-QA reviews visual diff and compliance
  "

echo ""
echo "✅ BANXE Hive Mind initialized and sprint started"
echo "   Monitor: npx claude-flow coordination metrics"
echo "   Status:  npx claude-flow agent-status"
