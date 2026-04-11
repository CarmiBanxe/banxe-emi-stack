#!/usr/bin/env bash
# bootstrap.sh — Create all required directories for banxe-emi-stack
# IL-SK-01 | Created: 2026-04-11

set -euo pipefail

echo "=== BANXE AI Bank — Bootstrap ==="

# Claude governance
mkdir -p .claude/rules
mkdir -p .claude/commands
mkdir -p .claude/specs
mkdir -p .claude/memory
mkdir -p .claude/agents
mkdir -p .claude/hooks
mkdir -p .claude/skills

# AI registries
mkdir -p .ai/registries
mkdir -p .ai/reports

# GitHub templates
mkdir -p .github/workflows
mkdir -p .github/ISSUE_TEMPLATE

# Documentation
mkdir -p docs/architecture
mkdir -p docs/compliance
mkdir -p docs/runbooks
mkdir -p docs/adr

# Infrastructure
mkdir -p infra/grafana/dashboards
mkdir -p infra/clickhouse/migrations
mkdir -p infra/postgres/migrations

# Application
mkdir -p services
mkdir -p agents/compliance/soul
mkdir -p agents/compliance/workflows
mkdir -p banxe_mcp
mkdir -p dbt/models
mkdir -p docker
mkdir -p scripts
mkdir -p mcp
mkdir -p n8n/workflows

echo "Bootstrap complete"
