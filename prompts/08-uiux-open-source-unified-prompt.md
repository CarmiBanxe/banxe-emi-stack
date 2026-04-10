# BANXE AI BANK — Unified UI/UX Open-Source Platform Prompt


## ROLE
Senior AI Implementation Orchestrator for EMI BANXE AI BANK.
Multi-agent collaboration: Claude Code, OpenClaw, MetaClaw, Ruff.
Task: Build production-grade web + mobile applications using open-source UI/UX stack.


## PRIMARY GOAL
Replace proprietary Sleek Design Skill with open-source stack.
Create reusable Claude Code workflow for:
1. Web + Mobile UI/UX generation
2. Monorepo architecture
3. Reusable design system
4. EMI banking compliance (PSD2, SCA, KYC, AML, GDPR)
5. Multi-agent compatibility (Claude Code, OpenClaw, MetaClaw, Codex)


## TARGET STACK


### Skills
- ui-ux-pro-max-skill (nextlevelbuilder) — cross-platform design intelligence
- exposkills (building-native-ui) — Expo/RN mobile UI
- vercel-labs/agent-skills (web-design-guidelines) — web UI audit
- ibelick/ui-skills (baseline-ui) — UI polish, accessibility
- frontend-design (Anthropic official) — frontend generation


### Architecture: Monorepo
```
banxe-platform/
  CLAUDE.md
  .claude/skills/
  packages/
    mobile/     — Expo + React Native + NativeWind + Expo Router
      CLAUDE.md
    web/        — Next.js 15 + Tailwind v4 + shadcn/ui
      CLAUDE.md
    shared/     — TypeScript types, API client, design tokens
```


### Tech
- TypeScript strict everywhere
- Expo SDK 53, Expo Router, NativeWind, gluestack-ui, Reanimated 3, Zustand
- Next.js 15 App Router, Tailwind CSS v4, shadcn/ui, Zustand
- pnpm workspaces + turbo
- Atomic Design (atoms/molecules/organisms)


## BRAND TOKENS
- Primary: #1A2B6B
- Accent: #00C6AE
- Background: #F5F7FA
- Font headings: Inter
- Font body: Roboto
- Standard: WCAG 2.1 AA


## BANKING EMI CONSTRAINTS
- PSD2 SCA two-step confirmation for ALL transactions
- KYC flows must match regulatory approval flow
- Biometric auth (expo-local-authentication)
- Certificate pinning enabled
- No raw card numbers stored client-side
- Consent screens GDPR + PSD2 compliant
- Session timeout UI (5-minute warning modal)
- No unsafe storage patterns
- No fake demo security assumptions
- Accessibility: keyboard navigation, ARIA labels on all interactive elements


## CLAUDE.MD REQUIREMENTS


### Root CLAUDE.md
- Repository architecture and package ownership
- Shared design rules and coding constraints
- Active skill references
- Banking UX constraints
- Conventional Commits format
- pnpm workspaces + turbo, never npm/yarn


### packages/mobile/CLAUDE.md
- Expo SDK 53 managed workflow
- Expo Router file-based navigation
- NativeWind (Tailwind for RN)
- gluestack-ui components
- Reanimated 3 animations (never Animated API)
- SafeAreaView from react-native-safe-area-context
- Icons: SF Symbols iOS, MD3 Android
- PSD2 SCA, biometric auth, certificate pinning
- KYC screens must match regulatory flow


### packages/web/CLAUDE.md
- Next.js 15 App Router
- TypeScript strict
- Tailwind CSS v4 + shadcn/ui
- Mobile-first responsive (320px-1440px)
- CSS variables for design tokens
- GDPR/PSD2 consent screens
- Session timeout UI
- Accessibility: keyboard nav, ARIA labels


## DESIGN SYSTEM


### Shared Tokens (packages/shared/design-tokens.ts)
- colors: primary, accent, background, surface, text, error, success
- typography: size scale, line-height, font-weight
- spacing: 4-point grid (4, 8, 12, 16, 24, 32, 48, 64)
- borderRadius: sm, md, lg, pill
- shadows: card, modal, button
- elevation tokens
- state colors (hover, active, disabled, error, success)


### Atomic Design Structure
- Atoms: Button, Input, Badge, Icon
- Molecules: Card, TransactionRow, AccountSelector
- Organisms: DashboardHeader, TransferForm, TransactionList


## UI SCAFFOLD TARGETS


### Mobile (Expo)
- app/auth/onboarding.tsx — 3 slides, Reanimated 3
- app/(tabs)/dashboard.tsx — balance, last 5 transactions, quick actions
- app/(tabs)/transfers.tsx — IBAN input, PSD2 SCA confirmation
- app/kyc/index.tsx — document upload, liveness check, selfie
- app/(tabs)/settings.tsx — biometric toggle, security
- Card Management screen
- Haptic feedback, Skeleton loaders, NativeWind


### Web (Next.js)
- app/auth/login/page.tsx — email + PIN
- app/dashboard/page.tsx — responsive 320px-1440px
- app/transfers/page.tsx — PSD2 consent flow
- app/settings/page.tsx — profile, security, preferences
- Consent/confirmation flows (GDPR + PSD2)
- shadcn/ui + Tailwind v4


## DEVELOPER BLOCK INTELLIGENCE SYSTEM


### 7 Capabilities
1. CODE DISCOVERY — scan all modules, endpoints, models, agents
2. PRODUCT EXTRACTION — infer product entities from code
3. DOMAIN CLASSIFICATION — finance / legal / shared / infra / agent
4. ARCHITECTURE REGISTRY — persistent structured registries
5. CHANGE TRACKING — detect new/changed code, update registries
6. WEB/MOBILE BUILD READINESS — what can build web/iOS/Android
7. AGENT HANDOFF — structured context for Claude Code, OpenClaw, MetaClaw, Codex


### Required Registries (.ai/registries/)
- workspace-map.md
- projects-map.md
- domain-map.md
- product-map.md
- api-map.md
- ui-map.md
- web-map.md
- mobile-map.md
- shared-map.md
- dependency-map.md
- change-log.md
- agent-map.md


### Required Reports (.ai/reports/)
- current-system-summary.md
- product-readiness-summary.md
- mobile-web-gap-analysis.md
- finance-domain-summary.md
- ui-build-readiness.md


## MULTI-AGENT COMPATIBILITY


### Claude Code
- Primary orchestrator
- Skills-based workflow (.claude/skills/)
- CLAUDE.md at root + package levels
- Expo MCP: claude mcp add --transport http expo-mcp https://mcp.expo.dev/mcp


### OpenClaw / MetaClaw
- Read registries from .ai/registries/
- Refresh summaries
- Detect stale mappings
- Build features from structured context


### Ruff
- Python code quality for backend (banxe-emi-stack)
- Pre-commit + CI integration


### Skills as Reusable Workflows
- banxe-code-intelligence — scan, classify, track code
- banxe-ui-bootstrap — web/mobile UI scaffold generation


## PHASED EXECUTION WORKFLOW


### PHASE 0 — DISCOVERY (DO NOT MODIFY FILES)
1. Inspect repository structure
2. Identify package manager, framework state
3. Inspect existing CLAUDE.md, .claude/, skills
4. Inspect existing web/mobile/shared structure
5. Detect project boundaries and domain boundaries
6. Identify blockers, risks, missing pieces
Output: current state summary + proposed plan
Wait for approval.


### PHASE 1 — PLAN
- Step-by-step implementation plan
- Separate root/shared/mobile/web changes
- Mark dependencies between stages
- Identify install commands and validation methods


### PHASE 2 — MONOREPO SETUP
```bash
mkdir banxe-platform && cd banxe-platform
pnpm init
cat > pnpm-workspace.yaml << EOF
packages:
  - 'packages/*'
EOF
mkdir -p packages/shared packages/web packages/mobile
cd packages/mobile && npx create-expo-app . --template tabs
```


### PHASE 3 — SKILLS INSTALLATION
```bash
npx skills add nextlevelbuilder/ui-ux-pro-max-skill
npx skills add vercel-labs/agent-skills
npx skills add ibelick/ui-skills
claude plugin marketplace add exposkills
claude plugin install expo
claude mcp add --transport http expo-mcp https://mcp.expo.dev/mcp
```


### PHASE 4 — CLAUDE.MD + DESIGN SYSTEM
- Create 3 CLAUDE.md files (root, mobile, web)
- Create packages/shared/design-tokens.ts
- Create packages/shared/theme.ts
- Component taxonomy plan


### PHASE 5 — UI SCAFFOLD
- Mobile starter screens (Expo)
- Web starter pages (Next.js)
- Prompt-ready blueprints if full implementation premature


### PHASE 6 — REGISTRIES + INTELLIGENCE
- Populate .ai/registries/ (12 files)
- Generate .ai/reports/ (5 files)
- Set up change tracking workflow


### PHASE 7 — VALIDATION
PASS A (Technical): repo structure, skill paths, CLAUDE.md scope, compatibility
PASS B (Product/UX): banking relevance, web/mobile consistency, accessibility, maintainability


### PHASE 8 — HANDOFF
1. Completed work
2. Changed files
3. Remaining manual actions
4. Exact commands
5. Exact verification commands
6. Next prompt to continue


## MANDATORY RULES
1. Never start coding without PHASE 0 discovery
2. Never skip repository inspection
3. Prefer incremental changes over large rewrites
4. Never claim a command succeeded without checking
5. Never commit secrets, use .env files
6. Tests required for all financial logic
7. Conventional Commits format
8. No destructive changes to existing services/, api/, tests/, agents/compliance/
9. Keep CLAUDE.md files compact and scoped
10. If manual action needed, output: ACTION REQUIRED / WHY / EXACT COMMAND / HOW TO VERIFY / WHAT I WILL DO NEXT


## INSTALLATION COMMANDS (REFERENCE)
```bash
# Skills
npx skills add nextlevelbuilder/ui-ux-pro-max-skill
npx skills add vercel-labs/agent-skills
npx skills add ibelick/ui-skills


# Expo plugins
claude plugin marketplace add exposkills
claude plugin install expo


# Expo MCP
claude mcp add --transport http expo-mcp https://mcp.expo.dev/mcp


# Color token MCP
npm install tokven-mcp


# EAS CLI (mobile deploy)
npm install -g eas-cli
```


## START INSTRUCTION
Begin with PHASE 0 only. Inspect the repository. Do not modify files yet.
After discovery, show the plan and wait for approval before structural changes.