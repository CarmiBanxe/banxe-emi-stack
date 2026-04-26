# BANXE Design System
<!-- Single Source of Truth for UI across Web and Mobile -->
<!-- IL-UI-01 | Version: 1.1.0 | Date: 2026-04-27 -->
<!-- Canonical token source: frontend/src/design-system/DESIGN.md + tokens.css -->

---

## Design Tokens (MD3)

> Full CSS custom properties live in `frontend/src/design-system/tokens.css`.
> This file maps BANXE tokens → MD3 roles for cross-platform consistency.

### Colour Tokens

| MD3 Role              | BANXE Token                    | Value                     | Usage                           |
|-----------------------|-------------------------------|---------------------------|---------------------------------|
| `primary`             | `--color-brand-accent`        | `#3b82f6`                 | CTAs, focus rings, links        |
| `on-primary`          | `--color-text-primary`        | `oklch(95% 0 0)`          | Text on brand surfaces          |
| `primary-container`   | `--color-brand-primary`       | `oklch(30% 0.08 240)`     | Sidebar active state            |
| `surface`             | `--color-bg-card`             | `oklch(15% 0.01 240)`     | Card/panel backgrounds          |
| `surface-dim`         | `--color-bg-secondary`        | `oklch(13% 0.01 240)`     | Recessed surfaces                |
| `surface-bright`      | `--color-bg-tertiary`         | `oklch(17% 0.01 240)`     | Elevated surfaces               |
| `background`          | `--color-bg-primary`          | `oklch(10% 0 0)`          | Page background                 |
| `error`               | `--color-danger`              | `#f43f5e`                 | Errors, rejected states         |
| `on-error`            | `--color-text-danger`         | `#f87171`                 | Text on error surfaces          |
| `outline`             | `--color-border-default`      | `oklch(20% 0.01 240)`     | Borders, dividers               |
| `outline-variant`     | `--color-border-subtle`       | `oklch(17% 0.01 240)`     | Subtle separators               |

### Status / Semantic Colours

| State          | Token                     | Hex        | MD3 Equivalent       |
|----------------|--------------------------|------------|----------------------|
| Positive/green | `--color-success`        | `#10b981`  | `tertiary`           |
| Warning/amber  | `--color-warning`        | `#f59e0b`  | `secondary`          |
| Negative/red   | `--color-danger`         | `#f43f5e`  | `error`              |
| Info/blue      | `--color-info`           | `#3b82f6`  | `primary`            |
| High severity  | `--color-alert`          | `#f97316`  | (custom orange)      |

**Colour coding rule**: green = positive/APPROVED, red = negative/REJECTED/FLAGGED, amber = pending/warning, blue = informational/UNDER_REVIEW.

### AML Severity Palette

| Severity | Token                          | Hex        |
|----------|-------------------------------|------------|
| CRITICAL | `--color-severity-critical`   | `#f43f5e`  |
| HIGH     | `--color-severity-high`       | `#f97316`  |
| MEDIUM   | `--color-severity-medium`     | `#f59e0b`  |
| LOW      | `--color-severity-low`        | `oklch(45% 0 0)` |

### Typography (MD3 Type Scale)

| MD3 Role        | Font Family          | Size   | Weight | Usage                   |
|-----------------|---------------------|--------|--------|-------------------------|
| `display-large` | DM Serif Display    | 36px   | 400    | Hero headings           |
| `headline-medium`| DM Serif Display   | 24px   | 400    | Page titles             |
| `title-large`   | Inter               | 20px   | 600    | Section headings        |
| `title-medium`  | Inter               | 16px   | 600    | Card headings           |
| `body-large`    | Inter               | 16px   | 400    | Body copy               |
| `body-medium`   | Inter               | 14px   | 400    | Tables, data labels     |
| `label-small`   | Inter               | 12px   | 600    | Uppercase labels        |
| `mono`          | JetBrains Mono      | 14px   | 400    | IDs, audit trail        |

Financial figures always use `font-variant-numeric: tabular-nums`.

### Spacing (4px base grid)

`4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 48 / 64 px`
Tokens: `--spacing-1` through `--spacing-16`.

### Shape (MD3 Shape Scale)

| MD3 Role       | Token          | Value  | Usage              |
|----------------|---------------|--------|--------------------|
| `shape-small`  | `--radius-sm` | 4px    | Badges, chips      |
| `shape-medium` | `--radius-md` | 6px    | Inputs, rows       |
| `shape-large`  | `--radius-lg` | 8px    | Modals, drawers    |
| `shape-xl`     | `--radius-xl` | 12px   | Cards, panels      |
| `shape-full`   | `--radius-full`| 9999px| Pills, avatars     |

---

## Financial UI Rules

1. **Monetary values: Decimal only, never float.** Amounts cross service boundaries as strings (`DecimalString`). Python: `Decimal`. SQL: `Decimal(20,8)`. TypeScript display: `new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP" }).format(Number(amountStr))`.
2. **Tabular numerals required** on all financial figures: `font-variant-numeric: tabular-nums` + `font-feature-settings: "tnum" 1`. Use `.tabular-nums` utility or `[data-financial]` attribute.
3. **Currency prefix with non-breaking space**: `GBP 1,234.56` — never `£1234.56` (different spacing breaks alignment in tables).
4. **Colour-coded amounts**: positive → `--color-text-success`, negative → `--color-text-danger` + minus prefix, pending → `--color-text-warning` + italic.
5. **Disclosure header required** on every component that displays personal financial data (balance, transaction history, limits). Minimum: `"Data as of [timestamp] UTC"` in `label-small` muted style.

---

## Components Inventory

### Web — `frontend/src/` (existing, IL-ADDS-01)

| Component         | Path                                      | Tests                                  | Status   | MD3 Tokens |
|-------------------|------------------------------------------|----------------------------------------|----------|------------|
| `KPICard`         | `components/ui/KPICard.tsx`              | `__tests__/KPICard.test.tsx`           | ✅ Done  | Partial*   |
| `StatusBadge`     | `components/ui/StatusBadge.tsx`          | `__tests__/StatusBadge.test.tsx`       | ✅ Done  | Partial*   |
| `DataTable`       | `components/ui/DataTable.tsx`            | `__tests__/DataTable.test.tsx`         | ✅ Done  | Partial*   |
| `AMLAlertPanel`   | `components/ui/AMLAlertPanel.tsx`        | `__tests__/AMLAlertPanel.test.tsx`     | ✅ Done  | Partial*   |
| `Sidebar`         | `components/ui/Sidebar.tsx`              | —                                      | ✅ Done  | —          |
| `StepWizard`      | `components/ui/StepWizard.tsx`           | `__tests__/StepWizard.test.tsx`        | ✅ Done  | —          |
| `AuditTrail`      | `components/ui/AuditTrail.tsx`           | —                                      | ✅ Done  | —          |
| `ConsentToggle`   | `components/ui/ConsentToggle.tsx`        | `__tests__/ConsentToggle.test.tsx`     | ✅ Done  | —          |
| `DashboardPage`   | `modules/dashboard/DashboardPage.tsx`    | `__tests__/DashboardPage.test.tsx`     | ✅ Done  | —          |
| `KYCWizard`       | `modules/kyc/KYCWizard.tsx`              | `__tests__/KYCWizard.test.tsx`         | ✅ Done  | —          |
| `AMLMonitor`      | `modules/aml/AMLMonitor.tsx`             | —                                      | ✅ Done  | —          |

> *Partial: uses hardcoded oklch/hex values; migration to CSS var tokens tracked in IL-UI-01.

### Mobile — `apps/mobile/components/` (new, IL-UI-01)

| Component         | Path                                          | Status     |
|-------------------|----------------------------------------------|------------|
| —                 | `apps/mobile/components/`                    | 📂 Empty   |

### Web (apps/web) — `apps/web/components/` (new, IL-UI-01)

| Component         | Path                                         | Status     |
|-------------------|---------------------------------------------|------------|
| —                 | `apps/web/components/`                       | 📂 Empty   |

---

## Platform Conventions

### Web (Next.js / React 19)

- **Toolchain**: Vite 5, TypeScript 5.6, Tailwind CSS 3, Biome 2.3
- **Component path**: `apps/web/components/{Name}/index.tsx`
- **Test path**: `apps/web/components/{Name}/index.test.tsx`
- **State**: Zustand 5 (global), React Query 5 (server), `useState` (local)
- **Styling**: Tailwind utility classes + CSS vars from `tokens.css`; no hardcoded hex/oklch in components
- **Linter**: `npx biome check .` before commit

### Mobile (Expo / React Native)

- **Toolchain**: Expo SDK 53, TypeScript, React Native
- **Component path**: `apps/mobile/components/{Name}/index.tsx`
- **Test path**: `apps/mobile/components/{Name}/index.test.tsx`
- **Styling**: `StyleSheet.create` with token constants from `design-tokens.ts` (to be created)
- **No CSS vars**: React Native doesn't support CSS variables — use a shared `tokens.ts` that mirrors `tokens.css` values
- **Typecheck**: `npx expo typecheck` before commit

### Shared Rules (both platforms)

- Same `Props` interface exported from a shared `types.ts` where interfaces are identical
- Same MD3 colour roles — web via CSS vars, mobile via `tokens.ts` constants
- Financial amounts: always `string` at the component boundary (never `number`, never `Decimal` in props)
- Accessibility: `accessibilityLabel` / `aria-label` on all interactive and financial elements

---

## BANXE-specific Components to Build

| Component          | Web                                      | Mobile                                      | IL item    | Status  |
|--------------------|------------------------------------------|--------------------------------------------|------------|---------|
| `TransactionList`  | `apps/web/components/TransactionList/`   | `apps/mobile/components/TransactionList/`   | IL-UI-02   | [ ]     |
| `BalanceCard`      | `apps/web/components/BalanceCard/`       | `apps/mobile/components/BalanceCard/`       | IL-UI-02   | [ ]     |
| `KYCWizard`        | exists: `frontend/src/modules/kyc/`      | `apps/mobile/components/KYCWizard/`         | IL-ADDS-01 | [~] web |
| `AMLAlert`         | exists: `frontend/src/components/ui/`   | `apps/mobile/components/AMLAlert/`          | IL-ADDS-01 | [~] web |
| `PaymentForm`      | `apps/web/components/PaymentForm/`       | `apps/mobile/components/PaymentForm/`       | IL-UI-03   | [ ]     |
| `AccountDashboard` | `apps/web/components/AccountDashboard/`  | `apps/mobile/components/AccountDashboard/`  | IL-UI-03   | [ ]     |

> `[~]` = web-only exists, mobile version missing.

---

## WCAG AA Compliance (mandatory)

- Body text: minimum contrast ratio **4.5:1**
- Large text (18px+ regular, 14px+ bold): minimum **3:1**
- Focus indicators: `outline: 2px solid --color-border-focus; outline-offset: 2px`
- Error states: always **colour + icon + text** (never colour alone)
- Icon-only buttons: `aria-label` required

---

## References

| Artefact                                   | Purpose                              |
|--------------------------------------------|--------------------------------------|
| `frontend/src/design-system/DESIGN.md`     | Frontend-specific token spec         |
| `frontend/src/design-system/tokens.css`    | CSS custom properties (authoritative)|
| `frontend/tailwind.config.ts`              | Tailwind token mapping               |
| `frontend/src/__tests__/design-tokens.test.ts` | Token coverage verification     |
| `.claude/skills/material-3/SKILL.md`       | MD3 implementation guide             |
| `.claude/agents/ui-sync.md`                | Parallel web+mobile generator        |

---
*BANXE Design System v1.1.0 | IL-UI-01 | 2026-04-27*
