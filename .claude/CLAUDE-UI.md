# CLAUDE-UI.md — BANXE Frontend AI Agent Context
# IL-ADDS-01 | Version: 1.0.0 | Date: 2026-04-11

## Project Context

BANXE AI Bank — EMI Financial Analytics Frontend
FCA regulated EMI (Electronic Money Institution)
FCA CASS 15 safeguarding compliance required

## Design System

**ALWAYS reference `frontend/src/design-system/DESIGN.md`** before generating any UI code.

Key principles:
- Dark mode ONLY (all backgrounds use OKLCH color space)
- CSS tokens from `frontend/src/design-system/tokens.css`
- Tailwind config from `frontend/tailwind.config.ts`
- NO hardcoded hex values — use CSS custom properties only

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Framework | React 19 |
| Language | TypeScript (strict) |
| Styling | Tailwind CSS v4 |
| Build | Vite |
| State | Zustand |
| Server state | React Query |
| Forms | React Hook Form |
| Components | shadcn/ui + BANXE overrides |
| Charts | Recharts |
| Icons | Lucide React |
| Testing | Vitest + Playwright |
| Variant classes | class-variance-authority (CVA) |

## Module Status (THIS SPRINT)

| Module | Status | Path |
|--------|--------|------|
| Dashboard | ✅ IMPLEMENTED | `frontend/src/modules/dashboard/DashboardPage.tsx` |
| AML Monitor | ✅ IMPLEMENTED | `frontend/src/modules/aml/AMLMonitor.tsx` |
| KYC Wizard | ✅ IMPLEMENTED | `frontend/src/modules/kyc/KYCWizard.tsx` |
| Transactions | 🔜 Q2 2026 | — |
| Compliance Reports | 🔜 Q2 2026 | — |
| Settings | 🔜 Q2 2026 | — |

## Component Library

| Component | Path | Purpose |
|-----------|------|---------|
| StatusBadge | `components/ui/StatusBadge.tsx` | APPROVED/PENDING/REJECTED/FLAGGED/UNDER_REVIEW |
| KPICard | `components/ui/KPICard.tsx` | Large KPI number + sparkline |
| DataTable | `components/ui/DataTable.tsx` | Dense financial table |
| AMLAlertPanel | `components/ui/AMLAlertPanel.tsx` | Severity left-border alert |
| Sidebar | `components/ui/Sidebar.tsx` | 64px/240px nav sidebar |
| StepWizard | `components/ui/StepWizard.tsx` | Multi-step form wizard |
| ConsentToggle | `components/ui/ConsentToggle.tsx` | GDPR equal-weight consent |
| AuditTrail | `components/ui/AuditTrail.tsx` | Append-only audit log |

## Financial UI Rules (INVARIANTS)

1. **NEVER use float for monetary amounts** — integer minor units only
2. **ALL financial figures MUST use tabular-nums** — `font-variant-numeric: tabular-nums`
3. **Currency prefix with non-breaking space** — `GBP\u00a01,234.56`
4. **Negative amounts** — `--color-text-danger` (rose-400), minus prefix
5. **Pending amounts** — `--color-text-warning` (amber-400), italic style

## Compliance Rules (INVARIANTS)

6. **Consent flows** — EQUAL visual weight for Accept/Reject (GDPR Art.7)
7. **No dark patterns** — no pre-checked, no greyed-out Reject
8. **Audit trail** — monospace, read-only, append-only display
9. **WCAG AA** — 4.5:1 contrast minimum for ALL text
10. **Error states** — color + icon + text (never color alone)

## Agent Permissions

| Area | Permission |
|------|-----------|
| `frontend/src/` | READ + WRITE |
| `frontend/src/design-system/DESIGN.md` | READ ONLY (changelog required for changes) |
| `services/` | READ ONLY |
| `api/` | READ ONLY |
| `dbt/` | READ ONLY |
| `.env*` | NO ACCESS |

## NOT Implemented (out of scope this sprint)

- Real-time fraud ML scoring
- Analytics/BI dashboard (Metabase/Superset — P1)
- Mobile app
- PSD2 open banking flows
- Keycloak SSO integration
- WebSocket live updates

## Code Generation Guidelines

When generating React components:
1. Use TypeScript strict mode
2. Export named + default
3. Include JSDoc comment with purpose and IL reference
4. Prefer composition over inheritance
5. Use CSS custom properties — never hardcode hex
6. Add `aria-*` attributes for accessibility
7. Mobile-first responsive design

---
*Created: 2026-04-11 | IL-ADDS-01 | Prompt: 16*
