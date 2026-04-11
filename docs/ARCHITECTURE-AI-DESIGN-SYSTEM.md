# ARCHITECTURE — AI-Driven Design System (ADDS)

## Overview

AI-native design system for BANXE combining Google Stitch DESIGN.md,
Claude Code MCP integration, Ruflo multi-agent orchestration, and
OpenClaw persistent monitoring. Full open-source stack for fintech UI
generation with compliance-first approach.

## Problem Statement

BANXE needs a unified design system across Dashboard, AML Monitor,
KYC Wizard, Transaction Monitor, and Compliance Reports. Manual
design-to-code is slow, inconsistent, and cannot scale with
regulatory UI requirements (GDPR consent flows, PSD2 SCA, WCAG AA).

## Solution Architecture

```
Google Stitch / Penpot (Design Canvas)
  |
  v
DESIGN.md (plain-text design system - single source of truth)
  |
  +-- Stitch MCP Server --> Claude Code (reads design context)
  +-- Style Dictionary --> tokens.css / tailwind.config
  |
  v
[Claude Code + CLAUDE.md] (AI code generation)
  |
  +-- Dashboard Module
  +-- AML Monitor Module  
  +-- KYC Wizard Module
  +-- Transaction Monitor
  +-- Compliance Reports
  |
  v
[Ruflo Hive Mind] (8-agent parallel orchestration)
  |  Queen -> Architect -> 3x Coders -> Tester -> QA
  |
  v
[OpenClaw on GMKtec] (24/7 design monitoring)
  |  Screenshot diff, WCAG audit, dark pattern detection
  |
  v
BANXE Frontend (React 19 + Tailwind v4 + Vite)
```

## Core Components

### 1. DESIGN.md (Single Source of Truth)

Plain-text markdown design system readable by AI agents:
- Color tokens (OKLCH for dark mode, WCAG AA contrast)
- Typography (Inter + tabular-nums for financial data)
- Status badge system (APPROVED/PENDING/REJECTED/FLAGGED/UNDER_REVIEW)
- AML severity levels (CRITICAL/HIGH/MEDIUM/LOW via left-border accent)
- Spacing (4px base grid, 24px card padding)
- Component specs (data tables, KPI cards, step wizards, alert panels)
- Financial UI rules (no float, tabular-nums, currency formatting)
- Compliance UI patterns (equal-weight consent buttons, audit trail)

### 2. Stitch / Penpot MCP Server

- Google Stitch: AI-native canvas with DESIGN.md export
- Penpot: open-source fallback with official MCP Server
- MCP bridge: exposes design context to Claude Code
- Frames: 6 BANXE screens (Dashboard, AML, KYC, Transactions, Compliance, Settings)

### 3. Claude Code + CLAUDE.md

- CLAUDE.md: project context, module status, off-limits zones
- .mcp.json: Stitch/Penpot + PostgreSQL + GitHub + filesystem
- Generates UI code referencing DESIGN.md tokens
- Preserves existing business logic (style changes only)

### 4. Ruflo Hive Mind (Multi-Agent)

- 8-agent hierarchical topology (open-source, MIT)
- Queen Agent: orchestrates sprint
- Architect: plans component interfaces
- 3x Coders: Dashboard-Dev, AML-Dev, KYC-Dev (parallel)
- Tester: Playwright tests + WCAG AA validation
- Design-QA: visual diff against DESIGN.md
- SPARC methodology (Specification, Pseudocode, Architecture, Refinement, Completion)
- 75% API cost reduction vs sequential, 2.8-4.4x throughput

### 5. OpenClaw (24/7 Design Monitor)

- Self-hosted on GMKtec (MIT license, persistent memory)
- Scheduled: daily screenshot comparison across all modules
- On commit: check for hardcoded hex values, DESIGN.md drift
- Consent flow audit: detect dark patterns
- Telegram alerts on visual drift > 5%
- 90-day log retention (regulatory requirement)

## BANXE UI Modules

| Module | Frame | Key Components |
|--------|-------|----------------|
| Dashboard | banxe-dashboard-desktop | KPI cards, transaction table, AML alert feed |
| AML Monitor | banxe-aml-desktop | Alert table, risk matrix, case viewer |
| KYC Onboarding | banxe-kyc-flow | 5-step wizard, doc upload, verification |
| Transactions | banxe-transactions-desktop | Dense table, filters, inline actions |
| Compliance | banxe-compliance-desktop | Export panel, regulatory checklists |
| Settings | banxe-settings-desktop | Token management, webhook config |

## Technology Stack (All Open-Source or Free Tier)

| Layer | Tool | License | Cost |
|-------|------|---------|------|
| Design Canvas | Google Stitch 2.0 | Free | $0 |
| Design Fallback | Penpot (self-hosted) | MPL-2.0 | $0 |
| Design System | DESIGN.md (plain text) | - | $0 |
| MCP Protocol | Stitch MCP / Penpot MCP | Open source | $0 |
| Code Generation | Claude Code | Anthropic | API costs |
| Multi-Agent | Ruflo (claude-flow) | MIT | $0 |
| Design Monitor | OpenClaw | MIT | $0 |
| Frontend | React 19 + Tailwind v4 | MIT | $0 |
| Components | shadcn/ui + CVA | MIT | $0 |
| Charts | Recharts | MIT | $0 |
| Icons | Lucide React | ISC | $0 |
| Testing | Playwright + Loki | Apache/MIT | $0 |
| LLM Local | Ollama (qwen3, mixtral) | MIT | $0 |

## Regulatory Compliance

- GDPR Art.7: Equal-weight consent buttons (no dark patterns)
- PSD2 SCA: Transaction authentication UI flows
- WCAG AA: 4.5:1 contrast minimum for ALL text
- Consumer Duty PS22/9: Clear financial communication
- EU AI Act Art.52: Transparency in AI-generated UI
- FCA: Audit trail append-only display

## Files

- frontend/src/design-system/DESIGN.md - design tokens + rules
- frontend/src/design-system/tokens.css - CSS custom properties
- .claude/CLAUDE-UI.md - Claude Code UI project context
- .mcp-ui.json - MCP config (Stitch + PG + GitHub)
- .openclaw/skills/banxe-design-monitor.md - OpenClaw skill
- frontend/src/components/ - shadcn/ui + BANXE overrides
- frontend/src/modules/dashboard/ - Dashboard module
- frontend/src/modules/aml/ - AML Monitor module
- frontend/src/modules/kyc/ - KYC Wizard module
- infra/ruflo/ - Hive Mind config

---
*Created: 2026-04-11 | Ticket: IL-ADDS-01*
