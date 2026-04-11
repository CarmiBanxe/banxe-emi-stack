# BANXE Design System
# Single Source of Truth — AI-readable design tokens
# IL-ADDS-01 | Version: 1.0.0 | Date: 2026-04-11

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

### Text
- --color-text-primary: oklch(95% 0 0) /* near-white */
- --color-text-secondary: oklch(65% 0 0) /* slate-400 */
- --color-text-muted: oklch(45% 0 0) /* slate-500 */
- --color-text-danger: #f87171 /* rose-400 */
- --color-text-success: #34d399 /* emerald-400 */
- --color-text-warning: #fbbf24 /* amber-400 */

### Borders
- --color-border-default: oklch(20% 0.01 240) /* slate-700 */
- --color-border-subtle: oklch(17% 0.01 240) /* slate-800 */
- --color-border-focus: #3b82f6 /* blue-500 */

## Typography
- Display: DM Serif Display (headings only)
- Body: Inter (UI text, data)
- Data: Inter with font-variant-numeric: tabular-nums
- Mono: JetBrains Mono (IDs, audit trail)

### Font Sizes
- --font-size-xs: 0.75rem /* 12px */
- --font-size-sm: 0.875rem /* 14px */
- --font-size-base: 1rem /* 16px */
- --font-size-lg: 1.125rem /* 18px */
- --font-size-xl: 1.25rem /* 20px */
- --font-size-2xl: 1.5rem /* 24px */
- --font-size-3xl: 1.875rem /* 30px */
- --font-size-4xl: 2.25rem /* 36px */

### Font Weights
- --font-weight-normal: 400
- --font-weight-medium: 500
- --font-weight-semibold: 600
- --font-weight-bold: 700

## Spacing (4px base grid)
- --spacing-1: 0.25rem /* 4px */
- --spacing-2: 0.5rem /* 8px */
- --spacing-3: 0.75rem /* 12px */
- --spacing-4: 1rem /* 16px */
- --spacing-5: 1.25rem /* 20px */
- --spacing-6: 1.5rem /* 24px */
- --spacing-8: 2rem /* 32px */
- --spacing-10: 2.5rem /* 40px */
- --spacing-12: 3rem /* 48px */
- --spacing-16: 4rem /* 64px */

## Border Radius
- --radius-sm: 0.25rem /* 4px */
- --radius-md: 0.375rem /* 6px */
- --radius-lg: 0.5rem /* 8px */
- --radius-xl: 0.75rem /* 12px */
- --radius-full: 9999px

## Shadows (card elevation)
- --shadow-sm: 0 1px 2px 0 oklch(0% 0 0 / 0.3)
- --shadow-md: 0 4px 6px -1px oklch(0% 0 0 / 0.4), 0 2px 4px -2px oklch(0% 0 0 / 0.2)
- --shadow-lg: 0 10px 15px -3px oklch(0% 0 0 / 0.5), 0 4px 6px -4px oklch(0% 0 0 / 0.3)
- --shadow-glow-blue: 0 0 20px oklch(50% 0.2 240 / 0.3)

## Component Dimensions
- --sidebar-collapsed: 64px
- --sidebar-expanded: 240px
- --table-row-height: 44px
- --table-header-height: 40px
- --card-padding: 24px
- --kpi-card-height: 140px

## Financial UI Rules
1. NEVER use float for monetary amounts (integer minor units only)
2. ALL financial figures must use tabular-nums (font-variant-numeric: tabular-nums)
3. Currency prefix with non-breaking space: GBP 1,234.56
4. Negative amounts: --color-text-danger (rose-400), minus prefix
5. Pending amounts: --color-text-warning (amber-400), italic style

## Status Badges
| Status       | Color Token        | Icon          |
|-------------|-------------------|---------------|
| APPROVED    | --color-success   | Shield        |
| PENDING     | --color-warning   | Clock         |
| REJECTED    | --color-danger    | X             |
| FLAGGED     | --color-alert     | AlertTriangle |
| UNDER_REVIEW| --color-info      | Search        |

## AML Severity System
| Severity | Border Token                  | Background opacity |
|---------|------------------------------|-------------------|
| CRITICAL | --color-severity-critical    | 10%               |
| HIGH     | --color-severity-high        | 10%               |
| MEDIUM   | --color-severity-medium      | 8%                |
| LOW      | --color-severity-low         | 5%                |

## Data Tables (Dense Mode)
- Font: 14px Inter, tabular-nums
- Row height: 44px (--table-row-height)
- Header: 12px uppercase, letter-spacing 0.05em, --color-text-secondary
- Zebra rows: bg-secondary / bg-card alternating
- Sortable columns: arrow icon on hover, active direction indicator
- Batch actions: floating bar appears when ≥1 row selected
- Inline actions: Hold, Verify, Escalate, Export

## Navigation
- Left sidebar: 64px collapsed, 240px expanded
- Sections: Overview, Accounts, Transactions, AML, KYC, Compliance, Settings
- Active state: brand-accent left border + text-primary
- Collapsed: icons only with tooltip on hover

## Compliance UI Patterns

### Consent Toggles (GDPR Art.7)
- Accept and Reject buttons: IDENTICAL visual weight (same size, same contrast)
- No pre-checked states, no greyed-out reject options
- Dark patterns are STRICTLY PROHIBITED

### KYC Document Upload
- Show accepted formats prominently (PDF, JPG, PNG)
- Show max file size (10MB)
- Upload progress bar (0-100%)
- Error state: specific error message, not generic "upload failed"

### Audit Trail
- Font: JetBrains Mono (--font-mono)
- Display: timestamp (ISO 8601), user ID, action, resource
- Read-only: no edit/delete controls visible
- Append-only: newest entries at top
- 90-day retention indicator

### Risk Score Display
- Range: 0-100
- Numerical value prominent (tabular-nums, text-2xl)
- Color gradient: green (0-30) → amber (31-70) → rose (71-100)
- Verbal label: LOW / MEDIUM / HIGH / CRITICAL

## Accessibility (WCAG AA)
- Minimum contrast ratio: 4.5:1 for body text
- Minimum contrast ratio: 3:1 for large text (18px+ or 14px bold)
- All interactive elements: focus ring (--color-border-focus, 2px offset)
- Error states: color + icon + text (never color alone)
- Screen reader: aria-labels on all icon-only buttons

---
*Design System v1.0.0 | IL-ADDS-01 | 2026-04-11*
