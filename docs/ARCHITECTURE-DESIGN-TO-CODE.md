# ARCHITECTURE — Design-to-Code Pipeline (D2C)

## Overview

Open-source design-to-code pipeline replacing Figma MCP + Claude Code
with Penpot MCP Server + AI Orchestrator for automated UI generation
across BANXE web and mobile platforms.

## Problem Statement

Current UI development relies on manual Figma-to-code handoff.
Designers create mockups, developers manually extract spacing,
colors, typography and rebuild components from scratch.

**Result:** Slow iteration, design drift, inconsistent tokens,
no automation, vendor lock-in (Figma license).

## Solution: Penpot MCP + AI Design Pipeline

### Architecture Diagram

```
Penpot (self-hosted, Docker)
  |
  v
[Penpot MCP Server] <-- REST API + MCP Protocol
  |
  +-- Design Token Extractor --> Style Dictionary
  |                               |
  |                         tokens.css / tailwind.config
  |                               |
  +-- AI Orchestrator (FastAPI + LangChain)
  |     |
  |     +-- Penpot Context Reader (components, layout, styles)
  |     +-- Code Generator (Mitosis JSX -> React/Vue/RN)
  |     +-- Visual QA Agent (Puppeteer + ResembleJS)
  |     +-- Ollama LLM (local, qwen3/mixtral)
  |
  +-- Component Registry (Storybook)
  |
  +-- Visual Regression (Loki / BackstopJS)
  |
  v
BANXE Web (Next.js) + Mobile (Expo/RN)
```

## Core Components

### 1. Penpot (Design Tool)

- Self-hosted Docker deployment on GMKtec
- Native design tokens support (2025+)
- Official MCP Server (github.com/penpot/penpot)
- Plugin ecosystem: Penpot AVA (AI assistant), LocoAI (design-to-code)
- Figma import plugin for migration
- REST API: /api/rpc/command/<method>
- Auth: Bearer token via Access Tokens

### 2. Penpot MCP Server

- Official MCP protocol bridge (Smashing Magazine, Jan 2026)
- Python SDK + REST API + CLI tools
- Works with any MCP client (Claude Desktop, Cursor, VS Code)
- Capabilities:
  - Read design components, hierarchy, layout
  - Extract design tokens (colors, typography, spacing)
  - Understand auto-layout constraints
  - Bidirectional: design-to-code AND code-to-design
  - Design-to-documentation, documentation-to-design-system

### 3. Design Token Pipeline

```
Penpot Design Tokens (native)
  |
  v
Tokens Studio integration
  |
  v
Style Dictionary CLI
  |
  +-- tokens.css (CSS custom properties)
  +-- tailwind.config.ts (Tailwind theme)
  +-- tokens.json (raw JSON for RN StyleSheet)
  +-- tokens.swift / tokens.kt (native mobile)
```

### 4. AI Orchestrator (FastAPI)

Microservice that bridges Penpot MCP with code generation:

- GET /design/context/{file_id} - fetch design structure from Penpot
- POST /design/generate - AI generates component code
- POST /design/compare - visual QA (screenshot diff)
- POST /design/sync-tokens - sync tokens from Penpot to codebase
- GET /design/components - list all design components

LLM chain: get_design_context -> analyze_layout -> generate_code -> verify_screenshot

### 5. Code Generator

Multi-framework output via Builder.io Mitosis:
- Write once in Mitosis JSX
- Compile to: React, Vue, Svelte, React Native, Angular
- LocoAI plugin: direct Penpot-to-code (React, HTML/CSS, Next.js, Vue)
- TeleportHQ SDK: alternative code generator

### 6. Visual QA & Regression

- Loki: Storybook snapshot comparisons
- BackstopJS: screenshot diff against Penpot mockup
- ResembleJS: pixel-level comparison
- CI integration: GitHub Actions auto-compare on PR

### 7. Component Registry

- Storybook: component catalog + documentation
- NX monorepo: shared packages across web/mobile
- Auto-publish to npm (internal registry)

## BANXE-Specific UI Agents

| Agent | Purpose | Penpot Integration |
|-------|---------|--------------------|
| Compliance UI Agent | Generate compliant forms (KYC, AML) | Read compliance component library |
| Anti-Fraud UI Helper | Alert/dashboard layouts | Generate from fraud event schemas |
| Transaction UI Agent | Payment flows, SCA screens | PSD2-compliant form generation |
| Onboarding Agent | KYC step-by-step flows | Sequential screen generation |
| Report UI Agent | FIN060, SAR report layouts | Generate from data models |

## Technology Stack

| Layer | Technology | License |
|-------|-----------|--------|
| Design | Penpot 2.x | MPL-2.0 |
| MCP Bridge | Penpot MCP Server | Open source |
| Tokens | Style Dictionary + Tokens Studio | Apache 2.0 |
| AI Orchestrator | FastAPI + LangChain | MIT |
| LLM | Ollama (qwen3, mixtral) | MIT |
| Code Gen | Mitosis (Builder.io) | MIT |
| Code Gen Alt | LocoAI Penpot Plugin | Proprietary (free tier) |
| Components | Storybook 8.x | MIT |
| Visual QA | Loki + BackstopJS | MIT |
| Web | Next.js 15 + shadcn/ui | MIT |
| Mobile | Expo SDK 53 + NativeWind | MIT |
| Monorepo | pnpm + Turborepo | MIT |

## FCA/EU Regulatory References

- GDPR Art.25: Privacy by Design in UI (data minimization)
- PSD2 SCA: Transaction authentication UI requirements
- Consumer Duty PS22/9: Clear, fair communication in UI
- EU AI Act Art.52: Transparency in AI-generated content

## Files

- services/design_pipeline/ - AI Orchestrator service
- services/design_pipeline/penpot_client.py - Penpot MCP client
- services/design_pipeline/token_extractor.py - Design tokens extraction
- services/design_pipeline/code_generator.py - Mitosis/LocoAI bridge
- services/design_pipeline/visual_qa.py - Screenshot comparison
- config/design-tokens/ - Token definitions (JSON)
- config/penpot/ - Penpot connection config
- infra/penpot/ - Docker compose for self-hosted Penpot
- infra/grafana/dashboards/design-pipeline-metrics.json

---
*Created: 2026-04-11 | Ticket: IL-D2C-01*
