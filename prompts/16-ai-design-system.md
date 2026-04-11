# Prompt 16 — AI-Driven Design System (ADDS) — Part 1

> Ticket: IL-ADDS-01 | Branch: refactor/claude-ai-scaffold
> Architecture: docs/ARCHITECTURE-AI-DESIGN-SYSTEM.md
> Date: 2026-04-11

## Goal

Create BANXE AI-driven design system with DESIGN.md as single source of truth,
Claude Code + MCP integration, design tokens pipeline, and frontend component
library for Dashboard, AML Monitor, and KYC Wizard modules.

## Reference

Read `docs/ARCHITECTURE-AI-DESIGN-SYSTEM.md` before starting.
Follow the attached specification BANXE-x-Google-Stitch-Claude-Code.

## Phase 1 — DESIGN.md (Single Source of Truth)

Create `frontend/src/design-system/DESIGN.md`:

```markdown
# BANXE Design System

## Colors (OKLCH for dark mode)

### Backgrounds
- --color-bg-primary: oklch(10% 0 0) /* slate-950 */
- --color-bg-secondary: oklch(13% 0.01 240) /* slate-900 */
- --color-bg-tertiary: oklch(17% 0.01 240) /* slate-800 */
- --color-bg-card: oklch(15% 0.01 240) /* slate-850 */

### Brand
- --color-brand-primary: oklch(30% 0.08 240) /* deep indigo */
- --color-brand-accent: #3b82f6 /* blue-500 */

### Status System
- --color-success: #10b981 /* emerald-500, APPROVED */
- --color-warning: #f59e0b /* amber-500, PENDING */
- --color-danger: #f43f5e /* rose-500, REJECTED/FLAGGED */
- --color-info: #3b82f6 /* blue-500, UNDER_REVIEW */
- --color-alert: #f97316 /* orange-500, HIGH severity */

### AML Severity Borders
- --color-severity-critical: #f43f5e
- --color-severity-high: #f97316
- --color-severity-medium: #f59e0b
- --color-severity-low: oklch(45% 0 0)

## Typography
- Display: DM Serif Display (headings only)
- Body: Inter (UI text, data)
- Data: Inter with font-variant-numeric: tabular-nums
- Mono: JetBrains Mono (IDs, audit trail)

## Financial UI Rules
1. NEVER use float for monetary amounts (integer minor units)
2. ALL financial figures must use tabular-nums
3. Currency prefix with space: GBP 1,234.56
4. Negative amounts: rose-400, minus prefix
5. Pending amounts: amber-400, italic

## Status Badges
| Status | Color Token | Icon |
|--------|------------|------|
| APPROVED | --color-success | Shield |
| PENDING | --color-warning | Clock |
| REJECTED | --color-danger | X |
| FLAGGED | --color-alert | AlertTriangle |
| UNDER_REVIEW | --color-info | Search |

## Data Tables (Dense Mode)
- Font: 14px Inter, tabular-nums
- Row height: 44px
- Header: 12px uppercase, letter-spacing 0.05em, slate-400
- Zebra rows: slate-900/slate-850
- Sortable columns: arrow on hover
- Batch actions: floating bar when rows selected

## Navigation
- Left sidebar: 64px collapsed, 240px expanded
- Sections: Overview, Accounts, Transactions, AML, KYC, Compliance, Settings

## Compliance UI Patterns
- Consent toggles: ALWAYS equal visual weight for accept/reject
- KYC upload: show accepted formats, max file size, progress
- Audit trail: monospace, timestamp, user ID, action (read-only)
- Risk score: 0-100 numerical + color gradient + verbal label
```

## Phase 2 — Design Tokens CSS

Create `frontend/src/design-system/tokens.css`:
- All CSS custom properties from DESIGN.md
- OKLCH colors for backgrounds
- Status system tokens
- AML severity border tokens
- Typography tokens (font families, sizes, weights)
- Spacing tokens (4px base grid)
- Shadow tokens (card elevation)

Create `frontend/tailwind.config.ts`:
- Extend theme with DESIGN.md tokens
- Map --color-* to Tailwind utilities
- Add tabular-nums font variant utility
- Configure dark mode (class strategy)

## Phase 3 — Component Library (shadcn/ui + BANXE overrides)

Create `frontend/src/components/` with BANXE-specific components:

`ui/StatusBadge.tsx`:
- Props: status (APPROVED|PENDING|REJECTED|FLAGGED|UNDER_REVIEW)
- Uses DESIGN.md color tokens + Lucide icons
- CVA (class-variance-authority) for variants

`ui/KPICard.tsx`:
- Large number (tabular-nums, text-3xl)
- Label (text-xs uppercase)
- Delta vs previous period (green/red arrow)
- Sparkline chart (Recharts)

`ui/DataTable.tsx`:
- Dense mode (14px, 44px row height)
- Zebra rows, frozen headers
- Sortable columns with direction arrows
- Batch actions floating bar
- Inline actions (Hold, Verify, Escalate, Export)

`ui/AMLAlertPanel.tsx`:
- Severity left-border accent (CRITICAL/HIGH/MEDIUM/LOW)
- Timestamp, description, Review CTA

`ui/Sidebar.tsx`:
- Collapsed 64px, expanded 240px
- 7 sections with icons (Lucide React)
- Active state indicator

`ui/StepWizard.tsx`:
- 5-step KYC wizard
- Progress: completion percentage, not just step count
- Back/Next navigation with form validation
- Step states: completed, active, pending

`ui/ConsentToggle.tsx`:
- GDPR compliant: equal visual weight accept/reject
- No dark patterns (no greyed-out options)

`ui/AuditTrail.tsx`:
- Monospace font, timestamp, user ID, action
- Read-only, append-only display
- 90-day retention indicator

## Phase 4 — Dashboard Module

Create `frontend/src/modules/dashboard/DashboardPage.tsx`:
1. Left sidebar navigation (Sidebar component)
2. KPI cards row: Total Balance, Active Accounts, Pending Transactions, Open AML Alerts
   - Each: large number (tabular-nums), label, delta arrow, sparkline
3. Recent transactions table (last 20)
   - Columns: Date, Account, Description, Amount, Status badge
4. AML alert feed (right panel, 320px)
   - Severity left-border, timestamp, description, Review CTA
5. Dark mode only (this sprint)
6. Keep ALL existing API calls and data hooks intact
7. Style changes only - do not refactor business logic

Create `frontend/src/modules/aml/AMLMonitor.tsx`:
1. Dense alert table with severity system
2. Risk heatmap visualization
3. Case detail slide-out panel
4. Filters: severity, date range, status
5. Bulk actions: Escalate, Assign, Close

## Phase 5 — KYC Wizard Module

Create `frontend/src/modules/kyc/KYCWizard.tsx`:

5 steps using StepWizard component:
- Step 1: Personal Identity (name, DOB, nationality, tax ID)
- Step 2: Address Verification (country, address, proof doc upload)
- Step 3: AML Pre-screening (automated, progress animation, result badge)
- Step 4: Document Upload (passport/ID front+back, selfie)
  - Drag-drop zone, accepted formats (PDF, JPG, PNG), max 10MB
  - Upload progress bar
- Step 5: Review + Approval (summary, consent checkbox, Submit/Save Draft)

Progress indicator: step dots + percentage + estimated time remaining
Mobile responsive: single column below 768px
Use React Hook Form for validation
Use existing api/kyc endpoints for submission
Loading/error/success states for all API calls

## Phase 6 — MCP + Claude Code Config

Create `.mcp-ui.json`:
```json
{
  "mcpServers": {
    "stitch": {
      "command": "npx",
      "args": ["-y", "stitch-mcp-auto"],
      "env": { "GOOGLE_CLOUD_PROJECT": "banxe-design" }
    },
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "frontend/src"]
    },
    "postgres": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-postgres"],
      "env": { "POSTGRES_CONNECTION_STRING": "postgresql://banxe:password@localhost:5432/banxe_db" }
    }
  }
}
```

Create `.claude/CLAUDE-UI.md`:
- Project context: BANXE AI banking platform
- Design System: ALWAYS reference DESIGN.md
- Tech stack: React 19, TypeScript, Tailwind v4, Vite, Zustand, React Query
- Module status: Dashboard (THIS SPRINT), AML (THIS SPRINT), KYC (THIS SPRINT)
- Financial UI rules (5 rules from DESIGN.md)
- Agent permissions: read/write frontend/src, read-only compliance/backend
- NOT implemented: real-time fraud ML, analytics dashboard, mobile app, PSD2

## Phase 7 — OpenClaw Design Monitor

Create `.openclaw/skills/banxe-design-monitor.md`:
- Daily 09:00: screenshot each module (dashboard, aml, kyc)
- Compare against reference screenshots
- If visual diff > 5%: send Telegram alert
- On git commit: check DESIGN.md not modified without changelog
- Verify no hardcoded hex values in new components
- Flag consent flow changes to compliance review
- NEVER auto-fix production code (flag and report only)
- Keep all logs 90 days

## Phase 8 — Ruflo Hive Mind Config

Create `infra/ruflo/hive-init.sh`:
```bash
npx claude-flow hive init --topology hierarchical --agents 8 --memory-size 512MB
npx claude-flow coordination agent-spawn --type researcher --name Design-Researcher
npx claude-flow coordination agent-spawn --type architect --name UI-Architect
npx claude-flow coordination agent-spawn --type coder --name Dashboard-Dev
npx claude-flow coordination agent-spawn --type coder --name AML-Dev
npx claude-flow coordination agent-spawn --type coder --name KYC-Dev
npx claude-flow coordination agent-spawn --type tester --name UI-Tester
npx claude-flow coordination agent-spawn --type reviewer --name Design-QA
npx claude-flow coordination task-orchestrate --task "Complete BANXE UI Sprint" --strategy parallel
```

Create `infra/ruflo/queen-agent-context.md`:
- Sprint goal: Dashboard + AML Monitor + KYC Wizard
- Coordination rules: Researcher first, Architect second, 3 Coders parallel
- Error handling: Stitch MCP error -> fallback to DESIGN.md tokens
- Design-QA flags -> route back to coder with diff
- Never modify compliance/backend without user confirmation

## Phase 9 — Tests

Create `frontend/src/__tests__/`:
- `design-tokens.test.ts` - verify all DESIGN.md tokens exist in tokens.css
- `StatusBadge.test.tsx` - all 5 status variants render correctly
- `KPICard.test.tsx` - tabular-nums, delta display
- `DataTable.test.tsx` - sorting, zebra rows, batch actions
- `AMLAlertPanel.test.tsx` - severity border colors
- `StepWizard.test.tsx` - 5 steps navigation, validation
- `ConsentToggle.test.tsx` - equal weight buttons, no dark patterns
- `DashboardPage.test.tsx` - layout, KPI cards, table, alert feed
- `KYCWizard.test.tsx` - all 5 steps, file upload, responsive
- `wcag-audit.test.ts` - WCAG AA contrast ratios for all tokens

Minimum 60 tests. Playwright for E2E. Vitest for unit.

## Files Checklist

```
frontend/src/design-system/DESIGN.md
frontend/src/design-system/tokens.css
frontend/tailwind.config.ts
frontend/src/components/ui/StatusBadge.tsx
frontend/src/components/ui/KPICard.tsx
frontend/src/components/ui/DataTable.tsx
frontend/src/components/ui/AMLAlertPanel.tsx
frontend/src/components/ui/Sidebar.tsx
frontend/src/components/ui/StepWizard.tsx
frontend/src/components/ui/ConsentToggle.tsx
frontend/src/components/ui/AuditTrail.tsx
frontend/src/modules/dashboard/DashboardPage.tsx
frontend/src/modules/aml/AMLMonitor.tsx
frontend/src/modules/kyc/KYCWizard.tsx
.mcp-ui.json
.claude/CLAUDE-UI.md
.openclaw/skills/banxe-design-monitor.md
infra/ruflo/hive-init.sh
infra/ruflo/queen-agent-context.md
frontend/src/__tests__/ (10+ test files, 60+ tests)
```

## Verification

1. All DESIGN.md tokens mapped in tokens.css
2. WCAG AA contrast ratios pass for all text/background combos
3. No hardcoded hex values in components (use tokens only)
4. Consent flows have equal-weight buttons
5. All financial amounts use tabular-nums
6. Dashboard renders with dark mode
7. KYC wizard navigates all 5 steps
8. 60+ tests green

---
*Created: 2026-04-11 | Ticket: IL-ADDS-01 | Prompt: 16*
